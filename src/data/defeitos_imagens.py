# -*- coding: utf-8 -*-
"""
Camada de dados do catálogo de imagens de defeitos — tabela defeitos_imagens.

Cada tipo de defeito (valor da coluna REMONTE nos registros) tem UMA imagem de
referência, guardada como bytea diretamente no Postgres/Supabase. O catálogo é
pequeno e fixo, então dispensa o Supabase Storage: reusa a mesma camada
get_connection() de todo o resto do app.

A busca imagem⇆defeito é feita por uma CHAVE NORMALIZADA (slug): removemos o
prefixo "img", acentos, espaços e símbolos e passamos a maiúsculas. Assim
"imgRevelEsgarcando", "Revel Esgarçando" e "REVEL ESGARÇANDO" caem todos na
mesma chave "REVELESGARCANDO" — que é o que casa o defeito de um registro com a
sua imagem, mesmo com grafias diferentes entre a planilha e o nome do arquivo.

Camada isolada e defensiva: só lê/escreve em defeitos_imagens. Falhas de banco
propagam como DatabaseUnavailableError (traduzida em database.py); a UI nunca
recebe traceback cru.
"""

import base64
import logging
import re
import unicodedata

import streamlit as st
from sqlalchemy import text

from src.config.settings import CACHE_TTL_SECONDS
from src.data.database import (
    DEFEITOS_IMAGENS_DDL,
    DatabaseUnavailableError,
    get_connection,
)

logger = logging.getLogger(__name__)

_TABLE = "defeitos_imagens"


# ── Normalização (a chave de busca defeito ⇆ imagem) ──────────────────────────

def normalizar_defeito(nome: str) -> str:
    """
    Converte um nome de defeito (da planilha ou do nome do arquivo) na chave-slug
    usada para casar registro com imagem.

        'imgRevelEsgarcando' → 'REVELESGARCANDO'
        'Revel Esgarçando'   → 'REVELESGARCANDO'
        'PONTO ESTOURADO'    → 'PONTOESTOURADO'

    Remove o prefixo "img", acentos, espaços e qualquer símbolo, e sobe para
    maiúsculas. Retorna '' para entrada vazia/None.
    """
    if not nome:
        return ""
    s = str(nome).strip()
    s = re.sub(r"^img", "", s, flags=re.IGNORECASE)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]", "", s)
    return s.upper()


# ── Garantia de schema ────────────────────────────────────────────────────────

def _ensure_schema() -> None:
    """
    Garante a existência de defeitos_imagens de forma idempotente, executando a
    DDL a cada operação. Não usamos create_tables() (cacheada) aqui pelo mesmo
    motivo de historico_defeitos.py: após um hot-reload sem reinício do processo
    o cache pode ficar preso a um schema antigo. Rodar a DDL é barato.
    """
    with get_connection() as conn:
        conn.execute(text(DEFEITOS_IMAGENS_DDL))
        conn.commit()


# ── Leitura ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def carregar_catalogo() -> dict[str, dict]:
    """
    Carrega todo o catálogo já pronto para renderizar, indexado pela chave
    normalizada:

        { 'REVELESGARCANDO': {'nome': 'Revel Esgarçando',
                              'data_uri': 'data:image/png;base64,....'} }

    O data URI é montado aqui (uma vez, e cacheado) para que a tela de consulta
    só faça lookups baratos. Nunca levanta exceção para a UI: qualquer falha é
    logada e resulta em dict vazio.
    """
    try:
        _ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT chave_normalizada, defeito_nome, imagem_bytes, mime_type "
                    f"FROM {_TABLE}"
                )
            ).fetchall()
    except Exception:  # noqa: BLE001 — fronteira: nada de traceback cru na UI
        logger.exception("Falha ao carregar catálogo de imagens de defeitos")
        st.error(
            "⚠️ Não foi possível carregar as imagens dos defeitos agora. "
            "Tente novamente em instantes."
        )
        return {}

    catalogo: dict[str, dict] = {}
    for chave, nome, img_bytes, mime in rows:
        if not img_bytes:
            continue
        b64 = base64.b64encode(bytes(img_bytes)).decode()
        catalogo[chave] = {
            "nome": nome,
            "data_uri": f"data:{mime or 'image/png'};base64,{b64}",
        }
    return catalogo


def imagem_do_defeito(remonte: str, catalogo: dict[str, dict]) -> str | None:
    """Retorna o data URI da imagem do defeito, ou None se não houver cadastro."""
    return (catalogo.get(normalizar_defeito(remonte)) or {}).get("data_uri")


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def listar_defeitos() -> list[dict]:
    """
    Lista os defeitos já cadastrados (chave, nome), em ordem alfabética.
    Alimenta a seção de administração (ver/substituir/excluir). Retorna [] se
    vazio; falhas de banco propagam como DatabaseUnavailableError.

    Cacheado: invalidado explicitamente em salvar_imagem/excluir_imagem.
    """
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            text(
                "SELECT chave_normalizada, defeito_nome "
                f"FROM {_TABLE} ORDER BY LOWER(defeito_nome)"
            )
        ).fetchall()
    return [{"chave": r[0], "nome": r[1]} for r in rows]


# ── Escrita (upsert / exclusão) ───────────────────────────────────────────────

def salvar_imagem(uploaded_file, defeito_nome: str) -> str:
    """
    Cadastra (ou substitui) a imagem de um defeito. A chave normalizada é
    derivada de `defeito_nome`; se já existir cadastro para essa chave, a imagem
    e o rótulo são atualizados (upsert por chave_normalizada).

    Retorna a chave normalizada gravada. Levanta ValueError para entrada
    inválida (nome vazio, arquivo sem bytes). Falhas de banco propagam como
    DatabaseUnavailableError para a fronteira de erro da página.
    """
    if not defeito_nome or not defeito_nome.strip():
        raise ValueError("Informe o nome do defeito.")

    chave = normalizar_defeito(defeito_nome)
    if not chave:
        raise ValueError(
            "O nome do defeito não gerou uma chave válida (use letras ou números)."
        )

    img_bytes = uploaded_file.read()
    if not img_bytes:
        raise ValueError("O arquivo de imagem está vazio.")

    mime = getattr(uploaded_file, "type", None) or "image/png"

    _ensure_schema()
    with get_connection() as conn:
        conn.execute(
            text(
                f"INSERT INTO {_TABLE} "
                "(chave_normalizada, defeito_nome, imagem_bytes, mime_type) "
                "VALUES (:chave, :nome, :img, :mime) "
                "ON CONFLICT (chave_normalizada) DO UPDATE SET "
                "defeito_nome = EXCLUDED.defeito_nome, "
                "imagem_bytes = EXCLUDED.imagem_bytes, "
                "mime_type    = EXCLUDED.mime_type, "
                "atualizado_em = CURRENT_TIMESTAMP"
            ),
            {"chave": chave, "nome": defeito_nome.strip(), "img": img_bytes, "mime": mime},
        )
        conn.commit()

    carregar_catalogo.clear()
    listar_defeitos.clear()
    return chave


def excluir_imagem(chave_normalizada: str) -> int:
    """
    Remove o cadastro de imagem de um defeito. Retorna o número de linhas
    afetadas (0 ou 1). Falhas de banco propagam como DatabaseUnavailableError.
    """
    if not chave_normalizada:
        return 0

    _ensure_schema()
    with get_connection() as conn:
        result = conn.execute(
            text(f"DELETE FROM {_TABLE} WHERE chave_normalizada = :chave"),
            {"chave": chave_normalizada},
        )
        affected = result.rowcount
        conn.commit()

    if affected:
        carregar_catalogo.clear()
        listar_defeitos.clear()
    return affected
