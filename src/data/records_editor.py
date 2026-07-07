# -*- coding: utf-8 -*-
"""
Edição/correção manual da tabela registros_defeitos — módulo isolado.

Escopo: esta camada só lê/escreve na tabela registros_defeitos. Nunca
toca historico_cobrancas nem pagamentos_concluidos — correções aqui são
para inconsistências de digitação (acentos, caracteres especiais, etc.)
na base ativa, não para o fluxo de cobrança/pagamento.

A tabela tem PK `id` (bigserial). Os edits individuais usam essa coluna
para localizar linhas com precisão — no Postgres não existe `rowid`, e o
`ctid` não é estável. A busca expõe o `id` sob o alias `_rowid` para manter
a interface consumida pela UI (que trata o valor como uma chave opaca).
"""

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.config.settings import COLS
from src.data.database import create_tables, get_connection

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
    """Invalida caches e re-sincroniza a df ativa em session_state."""
    st.cache_data.clear()

    from src.data.loader import load_data_from_disk
    load_data_from_disk.clear()

    df_reloaded = load_data_from_disk()
    if df_reloaded is not None:
        st.session_state["df"] = df_reloaded


# ── Unificação de valores (find & replace em massa) ───────────────────────────

def get_value_counts(column: str) -> pd.DataFrame:
    """
    Retorna os valores distintos de `column` em registros_defeitos com a
    quantidade de registros de cada um, ordenado alfabeticamente (case-insensitive).
    """
    if column not in _ALL_COLUMNS:
        raise ValueError(f"Coluna inválida: {column}")

    create_tables()
    with get_connection() as conn:
        # CORREÇÃO: Foi adicionado LOWER("{column}") como uma coluna temporária 
        # chamada "ordem_lower" no SELECT para permitir o agrupamento e ordenação corretos no Postgres.
        df = pd.read_sql(
            text(
                f'SELECT "{column}" AS valor, COUNT(*) AS qtd, LOWER("{column}") AS ordem_lower '
                f'FROM registros_defeitos '
                f'GROUP BY "{column}", LOWER("{column}") '
                f'ORDER BY ordem_lower'
            ),
            conn,
        )
    
    # Remove a coluna auxiliar para entregar o DataFrame idêntico ao formato original esperado pela UI
    if not df.empty:
        df = df.drop(columns=["ordem_lower"])
        
    return df


def rename_value(column: str, old_value: str, new_value: str) -> int:
    """
    Substitui `old_value` por `new_value` in `column` para todos os
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
        result = conn.execute(
            text(f'UPDATE registros_defeitos SET "{column}" = :new WHERE "{column}" = :old'),
            {"new": new_value, "old": old_value},
        )
        affected = result.rowcount
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
    a PK `id` (exposta como coluna `_rowid`) para permitir edição/gravação
    precisa por linha. Resultado limitado a `limit` linhas.
    """
    create_tables()

    clauses: list[str] = []
    params: dict = {}

    if supplier:
        clauses.append('"FORNECEDOR" = :supplier')
        params["supplier"] = supplier
    if date_from:
        clauses.append('"DATA DE PRODUÇÃO ACABAMENTO" >= :date_from')
        params["date_from"] = date_from.strftime("%Y-%m-%d")
    if date_to:
        clauses.append('"DATA DE PRODUÇÃO ACABAMENTO" <= :date_to')
        params["date_to"] = date_to.strftime("%Y-%m-%d")
    if order:
        clauses.append('"ORDEM MESTRE" LIKE :order')
        params["order"] = f"%{order}%"

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params["limit"] = limit

    with get_connection() as conn:
        df = pd.read_sql(
            text(
                f'SELECT id AS _rowid, * FROM registros_defeitos '
                f'{where_sql} '
                f'ORDER BY "DATA DE PRODUÇÃO ACABAMENTO" DESC LIMIT :limit'
            ),
            conn,
            params=params,
        )

    if df.empty:
        return df

    df = df.drop(columns=["id"], errors="ignore")  # mantém só o alias _rowid
    df[COLS["date"]] = pd.to_datetime(df[COLS["date"]], errors="coerce")
    df[COLS["quantity"]]  = pd.to_numeric(df[COLS["quantity"]], errors="coerce")
    df[COLS["value_brl"]] = pd.to_numeric(df[COLS["value_brl"]], errors="coerce")
    df[COLS["minutes"]]   = pd.to_numeric(df[COLS["minutes"]], errors="coerce")
    return df


def update_record_fields(rowid: int, updates: dict) -> bool:
    """
    Atualiza colunas específicas de um único registro de registros_defeitos,
    localizado pela PK `id` (recebida em `rowid`).
    """
    updates = {c: v for c, v in updates.items() if c in _ALL_COLUMNS}
    if not updates:
        return False

    create_tables()

    set_parts: list[str] = []
    params: dict = {}
    for i, (col, val) in enumerate(updates.items()):
        pname = f"v{i}"
        set_parts.append(f'"{col}" = :{pname}')
        params[pname] = val
    params["rid"] = int(rowid)

    with get_connection() as conn:
        result = conn.execute(
            text(f'UPDATE registros_defeitos SET {", ".join(set_parts)} WHERE id = :rid'),
            params,
        )
        affected = result.rowcount
        conn.commit()

    if affected:
        _sync_after_write()
    return affected > 0


def get_distinct_suppliers() -> list[str]:
    """Lista de fornecedores distintos em registros_defeitos, ordenada."""
    create_tables()
    with get_connection() as conn:
        # CORREÇÃO: Selecionamos também o LOWER("FORNECEDOR") dando o alias de "ordem_lower".
        # Com isso, o ORDER BY passa a usar a coluna explicitada no SELECT, validando as regras do Postgres.
        rows = conn.execute(
            text(
                'SELECT DISTINCT "FORNECEDOR", LOWER("FORNECEDOR") AS ordem_lower '
                'FROM registros_defeitos '
                'ORDER BY ordem_lower'
            )
        ).fetchall()
    return [r[0] for r in rows if r[0]]