# -*- coding: utf-8 -*-
"""
Camada de leitura do backup — coleta o conteúdo bruto de cada tabela.

Existe porque o plano gratuito do Supabase não oferece backup automático: a
exportação manual para Excel é, hoje, a única cópia dos dados fora do banco.
Por isso a prioridade aqui é FIDELIDADE e RESILIÊNCIA, não elegância:

  · lê a tabela inteira, com a coluna `id` inclusive — o backup precisa
    permitir recriar as linhas com as mesmas chaves em outro SGBD;
  · NÃO usa as leituras cacheadas das outras camadas (@st.cache_data com TTL
    de 60s): um backup tem de refletir o estado atual do banco, não o que
    estava em cache;
  · isola cada tabela: se uma falhar (ausente, permissão, timeout), as demais
    continuam sendo exportadas e a falha vira uma linha de status no manifesto.

A geração do arquivo em si fica em src/services/backup_exporter.py; este
módulo não conhece Excel nem Streamlit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd
from sqlalchemy import inspect, text

from src.data.database import DatabaseUnavailableError, get_connection

logger = logging.getLogger(__name__)

# ── Status possíveis de uma tabela no backup ─────────────────────────────────
STATUS_OK = "ok"            # tabela lida com registros
STATUS_VAZIA = "vazia"      # tabela existe, mas sem linhas (vira aba só com cabeçalho)
STATUS_AUSENTE = "ausente"  # tabela não existe neste banco
STATUS_ERRO = "erro"        # falha ao ler — as demais tabelas seguem normalmente


@dataclass(frozen=True)
class TabelaBackup:
    """Uma tabela incluída no backup e o rótulo mostrado ao usuário."""

    nome: str
    rotulo: str


# Ordem aqui é a ordem no manifesto e no .zip.
TABELAS_BACKUP: tuple[TabelaBackup, ...] = (
    TabelaBackup("registros_defeitos", "Base ativa de defeitos"),
    TabelaBackup("historico_defeitos", "Histórico permanente de defeitos"),
    TabelaBackup("historico_cobrancas", "Cobranças emitidas"),
    TabelaBackup("pagamentos_concluidos", "Pagamentos concluídos"),
    TabelaBackup("devolucoes", "Devoluções"),
    TabelaBackup("tb_divida_dividida", "Cobrança dividida — parte da empresa"),
    TabelaBackup("UserGal", "Usuários do sistema"),
)

# Tabelas deliberadamente fora do backup. Ficam registradas no manifesto para
# que quem restaurar saiba que a ausência foi uma decisão, não uma falha.
TABELAS_EXCLUIDAS: tuple[tuple[str, str], ...] = (
    (
        "defeitos_imagens",
        "Fora do backup por decisão do time: guarda as imagens em binário (bytea), "
        "que o Excel não comporta. As imagens são recadastradas pela própria "
        "página de Defeitos/Imagens no banco novo.",
    ),
)

# Tabelas cujo arquivo carrega material sensível — a UI e o próprio .xlsx
# avisam quem for guardar o backup.
AVISOS_SENSIVEIS: dict[str, str] = {
    "UserGal": (
        "ATENÇÃO: esta planilha contém o hash da senha (PBKDF2-HMAC-SHA256) e o "
        "salt de cada usuário. Não é senha em texto puro, mas é material sensível "
        "— guarde este backup em local restrito e não o compartilhe."
    ),
}


@dataclass
class ResultadoTabela:
    """Resultado da coleta de uma tabela: dados + o que contar no manifesto."""

    nome: str
    rotulo: str
    status: str
    df: pd.DataFrame | None = None
    # (coluna, tipo no banco) — serve de referência de DDL na restauração.
    colunas: list[tuple[str, str]] = field(default_factory=list)
    erro: str = ""

    @property
    def linhas(self) -> int:
        return 0 if self.df is None else int(len(self.df))

    @property
    def exportavel(self) -> bool:
        """Só tabelas lidas com sucesso viram arquivo dentro do .zip."""
        return self.status in (STATUS_OK, STATUS_VAZIA)


# ── Coleta ────────────────────────────────────────────────────────────────────

def _tipos_das_colunas(conn, nome: str) -> list[tuple[str, str]]:
    """
    Tipos declarados no banco, para o manifesto. É informação auxiliar: se a
    introspecção falhar, o backup continua — apenas sem os tipos daquela tabela.
    """
    try:
        return [(c["name"], str(c["type"])) for c in inspect(conn).get_columns(nome)]
    except Exception:  # noqa: BLE001 — metadado opcional, nunca derruba o backup
        logger.exception("Falha ao introspectar colunas de %s", nome)
        return []


def carregar_tabela(tabela: TabelaBackup) -> ResultadoTabela:
    """
    Lê uma tabela inteira. Nunca levanta: toda falha vira STATUS_ERRO com a
    mensagem já em português, para que uma tabela problemática não impeça o
    backup das outras.
    """
    try:
        with get_connection() as conn:
            if not inspect(conn).has_table(tabela.nome):
                logger.warning("Tabela %s ausente no banco — fora do backup", tabela.nome)
                return ResultadoTabela(tabela.nome, tabela.rotulo, STATUS_AUSENTE)

            # Nome vem de TABELAS_BACKUP (constante do código), não de entrada
            # do usuário. As aspas preservam a caixa alta de "UserGal".
            df = pd.read_sql(text(f'SELECT * FROM "{tabela.nome}"'), conn)
            colunas = _tipos_das_colunas(conn, tabela.nome)
    except DatabaseUnavailableError as exc:
        logger.exception("Banco indisponível ao ler %s", tabela.nome)
        return ResultadoTabela(tabela.nome, tabela.rotulo, STATUS_ERRO, erro=str(exc))
    except Exception:  # noqa: BLE001 — fronteira: uma tabela ruim não cancela o backup
        logger.exception("Falha ao ler a tabela %s para o backup", tabela.nome)
        return ResultadoTabela(
            tabela.nome,
            tabela.rotulo,
            STATUS_ERRO,
            erro="Não foi possível ler esta tabela. Veja os logs do servidor.",
        )

    status = STATUS_OK if len(df) else STATUS_VAZIA
    return ResultadoTabela(tabela.nome, tabela.rotulo, status, df=df, colunas=colunas)


def coletar_backup(
    progresso: Callable[[int, int, str], None] | None = None,
) -> list[ResultadoTabela]:
    """
    Coleta todas as tabelas de TABELAS_BACKUP, na ordem declarada.

    `progresso(feitas, total, nome)` é chamado após cada tabela — usado pela UI
    para a barra de progresso. Um callback que exploda não pode cancelar o
    backup, então a chamada é protegida.
    """
    total = len(TABELAS_BACKUP)
    resultados: list[ResultadoTabela] = []

    for i, tabela in enumerate(TABELAS_BACKUP, start=1):
        resultados.append(carregar_tabela(tabela))
        if progresso is not None:
            try:
                progresso(i, total, tabela.nome)
            except Exception:  # noqa: BLE001 — feedback visual nunca cancela o backup
                logger.exception("Callback de progresso do backup falhou")

    return resultados
