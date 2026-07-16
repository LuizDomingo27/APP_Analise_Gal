# -*- coding: utf-8 -*-
"""
Camada de dados do Histórico de Defeitos — tabela historico_defeitos.

Guarda o registro PERMANENTE e completo de todos os defeitos importados
diariamente. Diferente de registros_defeitos (base ativa, que pode ser
corrigida/reprocessada), esta tabela é um histórico imutável: os dados
nunca são apagados. A única alteração permitida é a correção de nomes de
fornecedores digitados incorretamente (acentos, grafia), via rename_supplier.

Esta é uma camada isolada: só lê/escreve em historico_defeitos. Toda falha
de banco é propagada como DatabaseUnavailableError (traduzida na camada
database.py) ou tratada de forma segura pela UI — o app nunca quebra por
uma exceção aqui.
"""

import io
import logging

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.config.settings import COLS
from src.data.database import (
    HISTORICO_DEFEITOS_DDL,
    DatabaseUnavailableError,
    get_connection,
)
from src.data.loader import _cast_types, _validate

logger = logging.getLogger(__name__)

_TABLE = "historico_defeitos"


# ── Garantia de schema ────────────────────────────────────────────────────────

def _ensure_schema() -> None:
    """
    Garante que a tabela historico_defeitos exista, de forma idempotente
    (CREATE TABLE IF NOT EXISTS), executando a DDL diretamente a cada operação.

    NÃO usamos create_tables() (decorada com @st.cache_resource) aqui de
    propósito: após um hot-reload do Streamlit sem reinício do processo, aquele
    cache pode ficar preso a um schema antigo — anterior à criação desta tabela —
    e nunca recriá-la, causando "relation historico_defeitos does not exist".
    Rodar a DDL idempotente é barato (a página é acessada por ação do usuário)
    e elimina essa classe de erro por completo.

    Qualquer falha de banco vem traduzida como DatabaseUnavailableError pela
    camada get_connection().
    """
    with get_connection() as conn:
        conn.execute(text(HISTORICO_DEFEITOS_DDL))
        conn.commit()


# ── Público: leitura ──────────────────────────────────────────────────────────

@st.cache_data
def load_historico() -> pd.DataFrame | None:
    """
    Carrega todo o histórico de defeitos da tabela historico_defeitos.
    Retorna um DataFrame limpo (tipos ajustados) ou None se estiver vazio.

    Nunca levanta exceção para a UI: qualquer falha (banco indisponível,
    tabela ausente, erro do pandas/psycopg2) é logada com detalhe técnico,
    exibida como mensagem amigável e resulta em None — o app nunca quebra.
    """
    try:
        _ensure_schema()
        with get_connection() as conn:
            df = pd.read_sql(f"SELECT * FROM {_TABLE}", conn)
    except Exception:  # noqa: BLE001 — fronteira: nada de traceback cru na UI
        logger.exception("Falha ao carregar historico_defeitos")
        st.error(
            "⚠️ Não foi possível carregar o histórico de defeitos agora. "
            "Tente novamente em instantes."
        )
        return None

    df = df.drop(columns=["id"], errors="ignore")
    if df.empty:
        return None
    return _cast_types(df)


@st.cache_data
def get_supplier_counts() -> pd.DataFrame:
    """
    Valores distintos de FORNECEDOR no histórico com a contagem de registros
    de cada um, ordenados alfabeticamente (case-insensitive).

    Colunas retornadas: `valor` (nome do fornecedor) e `qtd` (nº de registros).
    Alimenta o formulário de correção de nomes. Retorna DataFrame vazio se
    não houver dados.

    Cacheado: invalidado explicitamente em append_historico/rename_supplier
    (as únicas escritas que afetam a coluna FORNECEDOR desta tabela).
    """
    _ensure_schema()
    with get_connection() as conn:
        df = pd.read_sql(
            text(
                'SELECT "FORNECEDOR" AS valor, COUNT(*) AS qtd, '
                'LOWER("FORNECEDOR") AS ordem_lower '
                f'FROM {_TABLE} '
                'GROUP BY "FORNECEDOR", LOWER("FORNECEDOR") '
                'ORDER BY ordem_lower'
            ),
            conn,
        )
    if not df.empty:
        df = df.drop(columns=["ordem_lower"])
    return df


# ── Público: escrita (append diário) ──────────────────────────────────────────

def append_historico(uploaded_file) -> dict | None:
    """
    Recebe um UploadedFile (.xlsx) com registros do dia, valida, ajusta tipos,
    remove datas já presentes no histórico e insere apenas os registros novos.
    A persistência é imediata no Postgres. Nenhum dado existente é apagado.

    Retorna dict com:
        added      → int — registros novos inseridos
        duplicates → int — registros ignorados (data já existia no histórico)
        total      → int — total de registros no histórico após a inserção
    Ou None em caso de erro (mensagem já exibida ao usuário via st.error).
    """
    try:
        raw_bytes = uploaded_file.read()
        df_new = pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl")
        df_new = _validate(df_new)
        df_new = _cast_types(df_new)
    except ValueError as exc:
        st.error(f"❌ Arquivo inválido: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 — leitura de arquivo do usuário
        logger.exception("Falha ao ler planilha do histórico")
        st.error(f"❌ Erro ao ler arquivo: {exc}")
        return None

    date_col = COLS["date"]

    try:
        _ensure_schema()
        with get_connection() as conn:
            rows = conn.execute(
                text(f'SELECT DISTINCT "DATA DE PRODUÇÃO ACABAMENTO" FROM {_TABLE}')
            ).fetchall()
            existing_dates = {r[0] for r in rows if r[0]}

            new_dates_str = df_new[date_col].dt.strftime("%Y-%m-%d")
            mask_new = ~new_dates_str.isin(existing_dates)
            df_to_add = df_new[mask_new].copy()
            duplicates = int((~mask_new).sum())

            if not df_to_add.empty:
                df_to_add[date_col] = df_to_add[date_col].dt.strftime("%Y-%m-%d")
                df_to_add.to_sql(_TABLE, conn, if_exists="append", index=False)

            total = conn.execute(
                text(f"SELECT COUNT(*) FROM {_TABLE}")
            ).fetchone()[0]

            conn.commit()
    except DatabaseUnavailableError as exc:
        logger.exception("Falha ao gravar no historico_defeitos")
        st.error(f"⚠️ {exc}")
        return None
    except Exception:  # noqa: BLE001 — fronteira: nada de traceback cru na UI
        logger.exception("Erro inesperado ao gravar no historico_defeitos")
        st.error(
            "⚠️ Não foi possível importar os registros agora. "
            "Verifique o arquivo e tente novamente."
        )
        return None

    load_historico.clear()
    get_supplier_counts.clear()

    return {
        "added": int(len(df_to_add)),
        "duplicates": duplicates,
        "total": int(total),
    }


# ── Público: correção de nomes de fornecedores ────────────────────────────────

def rename_supplier(old_value: str, new_value: str) -> int:
    """
    Corrige o nome de um fornecedor em TODO o histórico: substitui old_value
    por new_value na coluna FORNECEDOR. Única mutação permitida nesta tabela
    (correção de grafia). Retorna o número de registros afetados.

    Levanta ValueError para entrada inválida (novo valor vazio). Falhas de
    banco propagam como DatabaseUnavailableError para a fronteira de erro.
    """
    if not new_value or not new_value.strip():
        raise ValueError("O novo nome do fornecedor não pode ser vazio.")
    if old_value == new_value:
        return 0

    _ensure_schema()
    with get_connection() as conn:
        result = conn.execute(
            text(f'UPDATE {_TABLE} SET "FORNECEDOR" = :new WHERE "FORNECEDOR" = :old'),
            {"new": new_value.strip(), "old": old_value},
        )
        affected = result.rowcount
        conn.commit()

    if affected:
        load_historico.clear()
        get_supplier_counts.clear()
    return affected
