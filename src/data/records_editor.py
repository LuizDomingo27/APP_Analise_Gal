# -*- coding: utf-8 -*-
"""
Edição/correção manual da tabela registros_defeitos — módulo isolado.

Escopo: esta camada só lê/escreve na tabela registros_defeitos. Nunca
toca historico_cobrancas nem pagamentos_concluidos — correções aqui são
para inconsistências de digitação (acentos, caracteres especiais, etc.)
na base ativa, não para o fluxo de cobrança/pagamento.

Como a tabela não tem chave primária declarada, os edits usam o rowid
implícito do SQLite para localizar linhas com precisão.
"""

from datetime import date

import pandas as pd
import streamlit as st

from src.config.settings import COLS, DB_PATH
from src.data.database import create_tables, get_connection
from src.data.github_sync import push_db_to_github

# ── Colunas de texto sujeitas a inconsistência de digitação ───────────────────
EDITABLE_TEXT_COLUMNS = [
    COLS["supplier"],
    COLS["material"],
    COLS["location"],
    COLS["defect"],
]

_TEXT_COL_LABELS = {
    COLS["supplier"]: "Fornecedor",
    COLS["material"]: "Material",
    COLS["location"]: "Local",
    COLS["defect"]:   "Remonte / Tipo de Defeito",
}

_ALL_COLUMNS = list(COLS.values())


def _sync_after_write() -> None:
    """Invalida caches e re-sincroniza a df ativa em session_state + GitHub."""
    st.cache_data.clear()

    from src.data.loader import load_data_from_disk
    load_data_from_disk.clear()

    df_reloaded = load_data_from_disk()
    if df_reloaded is not None:
        st.session_state["df"] = df_reloaded

    push_db_to_github(DB_PATH)


# ── Unificação de valores (find & replace em massa) ───────────────────────────

def get_value_counts(column: str) -> pd.DataFrame:
    """
    Retorna os valores distintos de `column` em registros_defeitos com a
    quantidade de registros de cada um, ordenado alfabeticamente — útil
    para localizar variações do mesmo fornecedor/material (com/sem acento,
    caracteres especiais, espaços extras etc.).
    """
    if column not in _ALL_COLUMNS:
        raise ValueError(f"Coluna inválida: {column}")

    create_tables()
    with get_connection() as conn:
        df = pd.read_sql(
            f'SELECT "{column}" AS valor, COUNT(*) AS qtd '
            f'FROM registros_defeitos '
            f'GROUP BY "{column}" '
            f'ORDER BY "{column}" COLLATE NOCASE',
            conn,
        )
    return df


def rename_value(column: str, old_value: str, new_value: str) -> int:
    """
    Substitui `old_value` por `new_value` em `column` para todos os
    registros de registros_defeitos que casarem exatamente. Retorna o
    número de linhas afetadas.
    """
    if column not in _ALL_COLUMNS:
        raise ValueError(f"Coluna inválida: {column}")
    if not new_value or not new_value.strip():
        raise ValueError("O novo valor não pode ser vazio.")
    if old_value == new_value:
        return 0

    create_tables()
    with get_connection() as conn:
        cur = conn.execute(
            f'UPDATE registros_defeitos SET "{column}" = ? WHERE "{column}" = ?',
            (new_value, old_value),
        )
        affected = cur.rowcount
        conn.commit()

    if affected:
        _sync_after_write()
    return affected


# ── Edição individual de registros ────────────────────────────────────────────

def search_records(
    supplier: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    order: str | None = None,
    limit: int = 500,
) -> pd.DataFrame:
    """
    Busca registros de registros_defeitos com filtros opcionais, incluindo
    o rowid do SQLite (coluna `_rowid`) para permitir edição/gravação
    precisa por linha. Resultado limitado a `limit` linhas.
    """
    create_tables()

    clauses: list[str] = []
    params: list = []

    if supplier:
        clauses.append('"FORNECEDOR" = ?')
        params.append(supplier)
    if date_from:
        clauses.append('"DATA DE PRODUÇÃO ACABAMENTO" >= ?')
        params.append(date_from.strftime("%Y-%m-%d"))
    if date_to:
        clauses.append('"DATA DE PRODUÇÃO ACABAMENTO" <= ?')
        params.append(date_to.strftime("%Y-%m-%d"))
    if order:
        clauses.append('"ORDEM MESTRE" LIKE ?')
        params.append(f"%{order}%")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection() as conn:
        df = pd.read_sql(
            f'SELECT rowid AS _rowid, * FROM registros_defeitos '
            f'{where_sql} '
            f'ORDER BY "DATA DE PRODUÇÃO ACABAMENTO" DESC LIMIT ?',
            conn,
            params=[*params, limit],
        )

    if df.empty:
        return df

    df[COLS["date"]] = pd.to_datetime(df[COLS["date"]], errors="coerce")
    df[COLS["quantity"]]  = pd.to_numeric(df[COLS["quantity"]], errors="coerce")
    df[COLS["value_brl"]] = pd.to_numeric(df[COLS["value_brl"]], errors="coerce")
    df[COLS["minutes"]]   = pd.to_numeric(df[COLS["minutes"]], errors="coerce")
    return df


def update_record_fields(rowid: int, updates: dict) -> bool:
    """
    Atualiza colunas específicas de um único registro de registros_defeitos,
    localizado pelo rowid do SQLite. `updates` é um dict {coluna: novo_valor}
    já contendo apenas os campos que de fato mudaram. Retorna True se a
    linha foi alterada.
    """
    updates = {c: v for c, v in updates.items() if c in _ALL_COLUMNS}
    if not updates:
        return False

    create_tables()
    set_sql = ", ".join(f'"{c}" = ?' for c in updates)
    with get_connection() as conn:
        cur = conn.execute(
            f'UPDATE registros_defeitos SET {set_sql} WHERE rowid = ?',
            (*updates.values(), int(rowid)),
        )
        affected = cur.rowcount
        conn.commit()

    if affected:
        _sync_after_write()
    return affected > 0


def get_distinct_suppliers() -> list[str]:
    """Lista de fornecedores distintos em registros_defeitos, ordenada."""
    create_tables()
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT DISTINCT "FORNECEDOR" FROM registros_defeitos '
            'ORDER BY "FORNECEDOR" COLLATE NOCASE'
        ).fetchall()
    return [r[0] for r in rows if r[0]]
