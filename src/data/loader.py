"""
Data loading layer.

Hierarquia de carregamento:
  1. load_data_from_disk()   → lê bd_principal.xlsx diretamente do disco (startup normal)
  2. append_new_data()       → valida + deduplica + salva registros novos na base existente
  3. load_data_from_upload() → usada apenas quando bd_principal.xlsx ainda não existe (1ª vez)
"""

import io
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config.settings import COLS, BD_PRINCIPAL, DATASET_DIR


# ── Público: carregamento do disco ────────────────────────────────────────────

@st.cache_data
def load_data_from_disk() -> pd.DataFrame | None:
    """
    Lê bd_principal.xlsx da pasta dataset/.
    Retorna DataFrame limpo, ou None se o arquivo não existir.
    """
    if not BD_PRINCIPAL.exists():
        return None
    try:
        df = pd.read_excel(BD_PRINCIPAL, engine="openpyxl")
        df = _validate(df)
        df = _cast_types(df)
        return df
    except ValueError as exc:
        st.error(f"❌ Base principal corrompida: {exc}")
        return None
    except Exception as exc:
        st.error(f"❌ Erro ao carregar base principal: {exc}")
        return None


def append_new_data(uploaded_file) -> dict | None:
    """
    Recebe um UploadedFile com novos registros, valida, deduplica e
    faz append na bd_principal.xlsx.

    Retorna dict com:
        added      → int  — registros novos gravados
        duplicates → int  — registros ignorados por já existirem
        total      → int  — total de registros após merge
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

    # Garante que a pasta dataset/ existe
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    date_col = COLS["date"]

    # ── Caso: base ainda não existe → primeira carga ──────────────────────────
    if not BD_PRINCIPAL.exists():
        _save_to_disk(df_new)
        load_data_from_disk.clear()
        return {"added": len(df_new), "duplicates": 0, "total": len(df_new)}

    # ── Caso: base já existe → backup + merge + deduplicação ─────────────────
    df_existing = pd.read_excel(BD_PRINCIPAL, engine="openpyxl")
    df_existing = _cast_types(df_existing)

    _backup()

    existing_dates = set(df_existing[date_col].dt.date)
    mask_new      = ~df_new[date_col].dt.date.isin(existing_dates)
    df_to_add     = df_new[mask_new]
    duplicates    = int((~mask_new).sum())

    df_merged = pd.concat([df_existing, df_to_add], ignore_index=True)
    _save_to_disk(df_merged)
    load_data_from_disk.clear()

    return {
        "added":      int(len(df_to_add)),
        "duplicates": duplicates,
        "total":      len(df_merged),
    }


def load_data_from_upload(uploaded_file) -> pd.DataFrame | None:
    """
    Lê um UploadedFile e retorna DataFrame limpo.
    Mantida como fallback e para uso direto no primeiro carregamento.
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


def _save_to_disk(df: pd.DataFrame) -> None:
    """Salva o DataFrame em bd_principal.xlsx."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df.to_excel(BD_PRINCIPAL, index=False, engine="openpyxl")


def _backup() -> None:
    """Cria cópia de segurança antes de qualquer operação de escrita."""
    if not BD_PRINCIPAL.exists():
        return
    backup = DATASET_DIR / "bd_principal_backup.xlsx"
    shutil.copy2(BD_PRINCIPAL, backup)
