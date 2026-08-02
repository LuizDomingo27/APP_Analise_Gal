# -*- coding: utf-8 -*-
"""
Geração do arquivo de backup: um .zip com um .xlsx por tabela + o manifesto.

Módulo puro — não importa Streamlit e não toca no banco. Recebe os resultados
já coletados por src/data/backup.py e devolve bytes. É o que torna o backup
testável de ponta a ponta sem subir a aplicação.

Duas preocupações guiam o código:

1. TIPO, não texto. Data vai para a célula como `datetime`, valor como `float`
   com formato de moeda, quantidade como `int`. Assim um `pd.read_excel` do
   arquivo devolve os mesmos dtypes — condição para a planilha servir de fonte
   numa restauração para outro SGBD. A conversão é "tudo ou nada" por coluna:
   se um único valor não converter, a coluna inteira fica como texto em vez de
   virar um misto silencioso de data e string.

2. Arquivo válido acima de tudo. Célula acima de 32.767 caracteres, caractere
   de controle e binário corrompem o .xlsx (ou fazem o openpyxl levantar) —
   são tratados na escrita, não deixados para o usuário descobrir ao abrir.

Nota de tema: a paleta aqui é hex literal de propósito. Planilha é um documento
próprio; `var(--ag-*)` não existe fora do HTML do app (ver src/config/theme.py).
"""

from __future__ import annotations

import io
import math
import zipfile
from datetime import date, datetime, time

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from src.data.backup import (
    AVISOS_SENSIVEIS,
    STATUS_AUSENTE,
    STATUS_ERRO,
    STATUS_OK,
    STATUS_VAZIA,
    TABELAS_EXCLUIDAS,
    ResultadoTabela,
)

# ── Paleta (mesma identidade de src/services/exporter.py) ────────────────────
_DARK_TEAL = "014B43"
_MID_TEAL = "099078"
_CREAM = "F9ECE5"
_WHITE = "FFFFFF"
_TEXT_DARK = "1A2E2A"
_BORDER_CLR = "D6E8E5"
_WARN_BG = "FFF4E5"
_WARN_TEXT = "8A5300"

# ── Limites do formato xlsx ──────────────────────────────────────────────────
_MAX_CELL_CHARS = 32_767
_TRUNC_MARK = "…[truncado]"
_MAX_SHEET_NAME = 31
_SHEET_FORBIDDEN = ':\\/?*[]'

# ── Formatos numéricos ───────────────────────────────────────────────────────
FMT_DATE = "DD/MM/YYYY"
FMT_DATETIME = "DD/MM/YYYY HH:MM"
FMT_MONEY = '"R$" #,##0.00'
FMT_DECIMAL = "#,##0.00"
FMT_INT = "#,##0"
FMT_PERCENT = "0.00%"

# Colunas com semântica conhecida do domínio. O resto é tipado pelo dtype.
_COLS_DATA = {
    "DATA DE PRODUÇÃO ACABAMENTO",
    "DATA_COBRANCA",
    "DATA_VENCIMENTO",
    "DATA_PAGAMENTO",
}
_COLS_DATA_HORA = {"created_at", "atualizado_em"}
_COLS_MOEDA = {"VALOR DO PROCESSO BRL"}
_COLS_DECIMAL = {"MINUTOS GERADOS"}
_COLS_INTEIRO = {"QUANTIDADE"}
# Guardado no banco como fração (0,12 = 12%) — o formato % faz a leitura.
_COLS_PERCENTUAL = {"PERCENTUAL DE REMONTE"}

# Colunas que devem permanecer TEXTO mesmo parecendo número: são identificadores,
# e convertê-las perderia zeros à esquerda ("00123") ou viraria notação científica.
_COLS_TEXTO = {"ORDEM MESTRE", "COD_LANCAMENTO", "CNPJ_FORNECEDOR", "CHAVE", "MATERIAL"}


# ── Estilo ────────────────────────────────────────────────────────────────────

def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _font(hex_color: str = _TEXT_DARK, bold: bool = False, size: int = 10) -> Font:
    return Font(name="Arial", color=hex_color, bold=bold, size=size)


def _border() -> Border:
    s = Side(style="thin", color=_BORDER_CLR)
    return Border(left=s, right=s, top=s, bottom=s)


def _center() -> Alignment:
    return Alignment(horizontal="center", vertical="center", wrap_text=True)


def _left() -> Alignment:
    return Alignment(horizontal="left", vertical="center")


# ── Saneamento de valores ─────────────────────────────────────────────────────

def _e_vazio(valor) -> bool:
    """True para None/NaN/NaT/string em branco — tudo vira célula vazia."""
    if valor is None:
        return True
    if isinstance(valor, float) and math.isnan(valor):
        return True
    if isinstance(valor, str):
        return not valor.strip()
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        # pd.isna de array/lista devolve array — não é "vazio", é valor composto.
        return False


def valor_celula(valor):
    """
    Converte um valor do DataFrame para algo que o openpyxl aceite gravar.

    Trata os quatro casos que corrompem (ou fazem explodir) o .xlsx:
    ausente → célula vazia; escalar numpy → tipo nativo; binário → descrição
    textual; texto longo ou com caractere de controle → truncado/limpo.
    """
    if _e_vazio(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(valor))} bytes — conteúdo binário não exportado>"
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, str):
        limpo = ILLEGAL_CHARACTERS_RE.sub("", valor)
        if len(limpo) > _MAX_CELL_CHARS:
            limpo = limpo[: _MAX_CELL_CHARS - len(_TRUNC_MARK)] + _TRUNC_MARK
        return limpo
    if isinstance(valor, (int, float, bool, datetime, date, time)):
        return valor
    # Tipos exóticos (Decimal, UUID, dict de jsonb...) viram texto legível.
    return valor_celula(str(valor))


# ── Tipagem por coluna (tudo ou nada) ─────────────────────────────────────────

def _tentar_datas(serie: pd.Series) -> pd.Series | None:
    """
    Converte a coluna inteira para datetime, ou devolve None se qualquer valor
    preenchido não for uma data ISO. O app grava datas como 'YYYY-MM-DD'; um
    formato diferente é sinal de dado sujo — nesse caso o backup preserva o
    texto original em vez de arriscar interpretar 05/07 como 7 de maio.
    """
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie
    limpa = serie.replace("", None)
    if limpa.dropna().empty:
        return None  # coluna toda vazia: nada a formatar, mantém como está
    try:
        return pd.to_datetime(limpa, format="ISO8601", errors="raise")
    except (ValueError, TypeError):
        return None


def _tentar_numerico(serie: pd.Series) -> pd.Series | None:
    """Numérico pela coluna inteira, ou None (mantém texto)."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie
    limpa = serie.replace("", None)
    if limpa.dropna().empty:
        return None
    try:
        return pd.to_numeric(limpa, errors="raise")
    except (ValueError, TypeError):
        return None


def preparar_coluna(nome: str, serie: pd.Series) -> tuple[pd.Series, str | None]:
    """
    Devolve (série pronta para escrita, formato numérico do Excel ou None).

    A ordem importa: colunas de identificador ficam como texto antes de qualquer
    tentativa de conversão, senão "ORDEM MESTRE" = 00123 perderia os zeros.
    """
    if nome in _COLS_TEXTO:
        return serie, None

    if nome in _COLS_DATA or nome in _COLS_DATA_HORA:
        convertida = _tentar_datas(serie)
        if convertida is not None:
            return convertida, FMT_DATE if nome in _COLS_DATA else FMT_DATETIME
        return serie, None

    if nome in _COLS_MOEDA or nome in _COLS_DECIMAL or nome in _COLS_PERCENTUAL or nome in _COLS_INTEIRO:
        convertida = _tentar_numerico(serie)
        if convertida is None:
            return serie, None
        if nome in _COLS_MOEDA:
            return convertida, FMT_MONEY
        if nome in _COLS_PERCENTUAL:
            return convertida, FMT_PERCENT
        if nome in _COLS_INTEIRO:
            return convertida, FMT_INT
        return convertida, FMT_DECIMAL

    # Sem semântica conhecida: respeita o dtype que veio do banco.
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie, FMT_DATE
    if pd.api.types.is_bool_dtype(serie):
        return serie, None
    if pd.api.types.is_integer_dtype(serie):
        return serie, FMT_INT
    if pd.api.types.is_float_dtype(serie):
        return serie, FMT_DECIMAL
    return serie, None


# ── Escrita de uma planilha ───────────────────────────────────────────────────

def _milhar(n: int) -> str:
    """1234 -> '1.234' (separador brasileiro), para os textos de subtítulo."""
    return f"{int(n):,}".replace(",", ".")


def nome_de_aba(nome: str) -> str:
    """Nome de aba válido: sem os caracteres proibidos e com no máximo 31 chars."""
    limpo = "".join("-" if c in _SHEET_FORBIDDEN else c for c in nome).strip() or "Tabela"
    return limpo[:_MAX_SHEET_NAME]


def _largura(coluna: str, valores: list) -> float:
    """Largura pelo conteúdo, com piso e teto para a planilha não ficar disforme."""
    maior = len(str(coluna))
    for v in valores[:200]:  # amostra: varrer 100 mil linhas não muda o resultado
        if v is not None:
            maior = max(maior, len(str(v)))
    return float(min(max(maior + 3, 12), 46))


def _faixa_titulo(ws: Worksheet, n_cols: int, titulo: str, subtitulo: str) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    tc = ws.cell(row=1, column=1)
    tc.value = titulo
    tc.font = _font(_WHITE, bold=True, size=12)
    tc.fill = _fill(_DARK_TEAL)
    tc.alignment = _center()
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    sc = ws.cell(row=2, column=1)
    sc.value = subtitulo
    sc.font = _font(_WHITE, size=9)
    sc.fill = _fill(_MID_TEAL)
    sc.alignment = _center()
    ws.row_dimensions[2].height = 16


def escrever_tabela(
    ws: Worksheet,
    df: pd.DataFrame,
    titulo: str,
    subtitulo: str,
    aviso: str = "",
) -> None:
    """
    Escreve o DataFrame na planilha com título, cabeçalho, zebra, autofiltro e
    formato numérico por coluna. Linha 1 título, 2 subtítulo, 3 cabeçalho
    (4 quando há aviso) e os dados na sequência.
    """
    colunas = list(df.columns)
    n_cols = max(len(colunas), 1)

    _faixa_titulo(ws, n_cols, titulo, subtitulo)

    linha_cabecalho = 3
    if aviso:
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=n_cols)
        ac = ws.cell(row=3, column=1)
        ac.value = f"⚠ {aviso}"
        ac.font = _font(_WARN_TEXT, bold=True, size=9)
        ac.fill = _fill(_WARN_BG)
        ac.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.row_dimensions[3].height = 26
        linha_cabecalho = 4

    for c, nome in enumerate(colunas, start=1):
        cell = ws.cell(row=linha_cabecalho, column=c)
        cell.value = str(nome).upper()
        cell.font = _font(_WHITE, bold=True, size=10)
        cell.fill = _fill(_DARK_TEAL)
        cell.alignment = _center()
        cell.border = _border()
    ws.row_dimensions[linha_cabecalho].height = 22

    primeira_linha = linha_cabecalho + 1
    for c, nome in enumerate(colunas, start=1):
        serie, formato = preparar_coluna(str(nome), df[nome])
        valores = [valor_celula(v) for v in serie.tolist()]

        for i, valor in enumerate(valores):
            cell = ws.cell(row=primeira_linha + i, column=c)
            cell.value = valor
            cell.font = _font(_TEXT_DARK)
            cell.border = _border()
            cell.fill = _fill(_CREAM if i % 2 else _WHITE)
            cell.alignment = _left() if isinstance(valor, str) else _center()
            if formato and valor is not None:
                cell.number_format = formato

        ws.column_dimensions[get_column_letter(c)].width = _largura(str(nome), valores)

    ultima_linha = max(primeira_linha + len(df) - 1, linha_cabecalho)
    ws.auto_filter.ref = (
        f"A{linha_cabecalho}:{get_column_letter(n_cols)}{ultima_linha}"
    )
    ws.freeze_panes = f"A{primeira_linha}"


# ── Planilha de uma tabela ────────────────────────────────────────────────────

def build_table_xlsx(resultado: ResultadoTabela, gerado_em: datetime) -> bytes:
    """Gera os bytes do .xlsx de UMA tabela do backup."""
    df = resultado.df if resultado.df is not None else pd.DataFrame()
    ts = gerado_em.strftime("%d/%m/%Y %H:%M")

    wb = Workbook()
    ws = wb.active
    ws.title = nome_de_aba(resultado.nome)

    subtitulo = (
        f"{resultado.rotulo}  ·  {_milhar(len(df))} registro(s)  ·  "
        f"{len(df.columns)} coluna(s)"
    )
    if resultado.status == STATUS_VAZIA:
        subtitulo += "  ·  tabela sem registros no momento do backup"

    escrever_tabela(
        ws,
        df,
        titulo=f"Backup · {resultado.nome}  ·  {ts}",
        subtitulo=subtitulo,
        aviso=AVISOS_SENSIVEIS.get(resultado.nome, ""),
    )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Manifesto ─────────────────────────────────────────────────────────────────

_ROTULO_STATUS = {
    STATUS_OK: "Exportada",
    STATUS_VAZIA: "Exportada (vazia)",
    STATUS_AUSENTE: "Ausente no banco",
    STATUS_ERRO: "Falhou",
}


def _resumo_dataframe(resultados: list[ResultadoTabela]) -> pd.DataFrame:
    linhas = [
        {
            "Tabela": r.nome,
            "Descrição": r.rotulo,
            "Status": _ROTULO_STATUS.get(r.status, r.status),
            "Registros": r.linhas,
            "Colunas": len(r.colunas) or (0 if r.df is None else len(r.df.columns)),
            "Arquivo no ZIP": f"{r.nome}.xlsx" if r.exportavel else "—",
            "Observação": r.erro or AVISOS_SENSIVEIS.get(r.nome, ""),
        }
        for r in resultados
    ]
    linhas += [
        {
            "Tabela": nome,
            "Descrição": "—",
            "Status": "Não incluída (decisão)",
            "Registros": 0,
            "Colunas": 0,
            "Arquivo no ZIP": "—",
            "Observação": motivo,
        }
        for nome, motivo in TABELAS_EXCLUIDAS
    ]
    return pd.DataFrame(linhas)


def _colunas_dataframe(resultados: list[ResultadoTabela]) -> pd.DataFrame:
    linhas = [
        {"Tabela": r.nome, "Coluna": coluna, "Tipo no banco": tipo}
        for r in resultados
        for coluna, tipo in r.colunas
    ]
    return pd.DataFrame(
        linhas or [{"Tabela": "—", "Coluna": "—", "Tipo no banco": "—"}]
    )


# Colunas de identificador guardadas como texto na planilha (ver _COLS_TEXTO).
# Quem reimportar com inferência automática de tipo transforma "00123" em 123 e
# perde os zeros à esquerda SEM ERRO NENHUM — por isso o aviso vai no manifesto,
# e não só no código.
_ORIENTACOES: tuple[tuple[str, str], ...] = (
    (
        "1. Estrutura",
        "Recrie as tabelas no banco novo usando a aba 'Colunas' como referência de "
        "tipos. Mantenha os nomes de coluna exatamente como estão (com acento, "
        "espaço e caixa alta) — o app procura por esses nomes.",
    ),
    (
        "2. Identificadores",
        "Ao ler as planilhas, force texto nas colunas de identificador "
        "(ORDEM MESTRE, COD_LANCAMENTO, CNPJ_FORNECEDOR, CHAVE): no pandas, "
        "pd.read_excel(arquivo, header=2, dtype=str). Sem isso, '00123' vira 123 "
        "e os zeros à esquerda somem silenciosamente.",
    ),
    (
        "3. Cabeçalho",
        "Em cada planilha os dados começam na 4ª linha: linha 1 é o título, 2 o "
        "subtítulo e 3 o cabeçalho (na planilha de usuários há um aviso a mais, "
        "e o cabeçalho fica na linha 4).",
    ),
    (
        "4. Chaves",
        "A coluna 'id' foi exportada de propósito: preserve-a para manter as "
        "referências entre as tabelas iguais às do banco de origem.",
    ),
    (
        "5. Imagens",
        "A tabela defeitos_imagens não faz parte deste backup. Recadastre as "
        "imagens pela própria página de Defeitos/Imagens depois da restauração.",
    ),
    (
        "6. Sigilo",
        "A planilha UserGal contém hash de senha e salt. Guarde o backup em local "
        "restrito; ele permite recriar os logins, mas não revela as senhas.",
    ),
)


def _orientacoes_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Etapa": etapa, "Orientação": texto} for etapa, texto in _ORIENTACOES]
    )


def build_info_xlsx(
    resultados: list[ResultadoTabela], gerado_em: datetime, gerado_por: str
) -> bytes:
    """
    Gera o manifesto do backup: o que foi exportado, quanto, e o tipo de cada
    coluna no banco de origem — a referência para recriar o schema no destino.
    """
    ts = gerado_em.strftime("%d/%m/%Y às %H:%M")
    total = sum(r.linhas for r in resultados)

    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"

    escrever_tabela(
        ws,
        _resumo_dataframe(resultados),
        titulo=f"Backup Análise Gal  ·  gerado em {ts}",
        subtitulo=(
            f"Gerado por: {gerado_por}  ·  {_milhar(total)} registro(s) no total  ·  "
            "um arquivo .xlsx por tabela neste .zip  ·  "
            "a aba 'Colunas' traz o tipo de cada campo no banco de origem"
        ),
    )

    ws_cols = wb.create_sheet("Colunas")
    escrever_tabela(
        ws_cols,
        _colunas_dataframe(resultados),
        titulo="Estrutura das tabelas exportadas",
        subtitulo="Use como referência de tipos ao recriar o schema em outro SGBD",
    )

    ws_como = wb.create_sheet("Como restaurar")
    escrever_tabela(
        ws_como,
        _orientacoes_dataframe(),
        titulo="Como restaurar este backup em outro banco",
        subtitulo="Leia antes de importar — o passo 2 evita perda silenciosa de dados",
    )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Pacote final ──────────────────────────────────────────────────────────────

def nome_do_arquivo(gerado_em: datetime) -> str:
    return f"backup_analise_gal_{gerado_em.strftime('%Y%m%d_%H%M')}.zip"


def build_backup_zip(
    resultados: list[ResultadoTabela],
    gerado_em: datetime | None = None,
    gerado_por: str = "—",
) -> bytes:
    """
    Monta o .zip do backup: `_INFO.xlsx` (manifesto) + um .xlsx por tabela lida
    com sucesso. Tabelas ausentes ou com erro não geram arquivo, mas aparecem
    no manifesto com o motivo.
    """
    gerado_em = gerado_em or datetime.now()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_INFO.xlsx", build_info_xlsx(resultados, gerado_em, gerado_por))
        for resultado in resultados:
            if not resultado.exportavel:
                continue
            zf.writestr(f"{resultado.nome}.xlsx", build_table_xlsx(resultado, gerado_em))

    return buf.getvalue()
