"""
Data loading layer.

Hierarquia de carregamento:
  1. load_data_from_disk()   → lê registros_defeitos do Postgres (startup normal)
  2. append_new_data()       → valida + deduplica + insere registros no Postgres
  3. load_data_from_upload() → fallback sem persistência (primeira importação)
"""

import io

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.config.settings import COLS
from src.data.database import DatabaseUnavailableError, create_tables, get_connection


# ── Público: carregamento do banco ────────────────────────────────────────────

@st.cache_data
def load_data_from_disk() -> pd.DataFrame | None:
    """
    Lê todos os registros da tabela registros_defeitos do Postgres.
    Retorna DataFrame limpo, ou None se a base estiver vazia.
    """
    try:
        create_tables()
        with get_connection() as conn:
            df = pd.read_sql("SELECT * FROM registros_defeitos", conn)
        df = df.drop(columns=["id"], errors="ignore")
        if df.empty:
            return None
        df = _cast_types(df)
        return df
    except Exception as exc:
        st.error(f"❌ Erro ao carregar base: {exc}")
        return None


def append_new_data(uploaded_file) -> dict | None:
    """
    Recebe um UploadedFile com novos registros, valida, deduplica por data e
    insere os registros novos na tabela registros_defeitos. A persistência é
    imediata no Postgres (sem sync externo).

    Retorna dict com:
        added      → int — registros novos inseridos
        duplicates → int — registros ignorados (data já existia na base)
        total      → int — total de registros na base após a inserção
    Ou None em caso de erro.
    """
    try:
        raw_bytes = uploaded_file.read()
        df_new    = pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl")
        df_new    = _validate(df_new)
        df_new    = _cast_types(df_new)
    except ValueError as exc:
        st.error(f"❌ Arquivo inválido: {exc}")
        return None
    except Exception as exc:
        st.error(f"❌ Erro ao ler arquivo: {exc}")
        return None

    date_col = COLS["date"]

    try:
        create_tables()

        with get_connection() as conn:
            rows = conn.execute(
                text('SELECT DISTINCT "DATA DE PRODUÇÃO ACABAMENTO" FROM registros_defeitos')
            ).fetchall()
            existing_dates = {r[0] for r in rows if r[0]}

            new_dates_str = df_new[date_col].dt.strftime("%Y-%m-%d")
            mask_new      = ~new_dates_str.isin(existing_dates)
            df_to_add     = df_new[mask_new].copy()
            duplicates    = int((~mask_new).sum())

            if not df_to_add.empty:
                df_to_add[date_col] = df_to_add[date_col].dt.strftime("%Y-%m-%d")
                df_to_add.to_sql("registros_defeitos", conn, if_exists="append", index=False)

            total = conn.execute(
                text("SELECT COUNT(*) FROM registros_defeitos")
            ).fetchone()[0]

            conn.commit()
    except DatabaseUnavailableError as exc:
        st.error(f"⚠️ {exc}")
        return None

    load_data_from_disk.clear()

    return {
        "added":      int(len(df_to_add)),
        "duplicates": duplicates,
        "total":      int(total),
    }


def load_data_from_upload(uploaded_file) -> pd.DataFrame | None:
    """
    Lê um UploadedFile e retorna DataFrame limpo sem persistir.
    Mantida como fallback.
    """
    try:
        raw_bytes = uploaded_file.read()
        df = pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl")
        df = _validate(df)
        df = _cast_types(df)
        return df
    except ValueError as exc:
        st.error(f"❌ Formato inválido: {exc}")
        return None
    except Exception as exc:
        st.error(f"❌ Erro ao ler o arquivo: {exc}")
        return None


# ── Privado ───────────────────────────────────────────────────────────────────

def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = list(COLS.values())
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas ausentes na planilha: {missing}")
    return df


def _cast_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[COLS["date"]]        = pd.to_datetime(df[COLS["date"]], errors="coerce")
    df[COLS["quantity"]]    = pd.to_numeric(df[COLS["quantity"]], errors="coerce").fillna(0).astype(int)
    df[COLS["value_brl"]]   = pd.to_numeric(df[COLS["value_brl"]], errors="coerce").fillna(0.0)
    df[COLS["minutes"]]     = pd.to_numeric(df[COLS["minutes"]], errors="coerce").fillna(0.0)
    df[COLS["pct_remonte"]] = pd.to_numeric(df[COLS["pct_remonte"]], errors="coerce").fillna(0.0)
    df[COLS["supplier"]]    = df[COLS["supplier"]].astype(str).str.strip()
    df[COLS["defect"]]      = df[COLS["defect"]].astype(str).str.strip()
    df[COLS["location"]]    = df[COLS["location"]].astype(str).str.strip()
    df.dropna(subset=[COLS["date"]], inplace=True)
    return df
