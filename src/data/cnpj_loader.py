"""
CNPJ lookup module.
Carrega Bd_Cnpj.xlsx e realiza busca do CNPJ pelo nome do fornecedor.
Estratégia de match: normalização + busca em múltiplas colunas de nome.
"""

import io
import unicodedata
from pathlib import Path

import pandas as pd

# ── Path do arquivo de referência (bundled com o app) ─────────────────────────
_CNPJ_FILE = Path(__file__).parent.parent.parent / "Bd_Cnpj.xlsx"

# Colunas de nome consultadas em ordem de prioridade
_NAME_COLS = [
    "Razão Social Postos",
    "Razão Social ABVTEX",
    "Razão Social Cadeia",
    "Nome Fantasia",
]
_CNPJ_COL = "CNPJ"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normaliza texto para comparação:
    - Remove espaços extras
    - Converte para maiúsculas
    - Remove acentos (NFD decomposition)
    """
    text = str(text).strip().upper()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# ── Public API ────────────────────────────────────────────────────────────────

def load_cnpj_db(file_bytes: bytes | None = None) -> pd.DataFrame | None:
    """
    Carrega a base de CNPJ.
    Prioridade: bytes fornecidos (upload) > arquivo bundled.
    Retorna DataFrame com colunas normalizadas ou None em caso de falha.
    """
    try:
        if file_bytes is not None:
            source = io.BytesIO(file_bytes)
        elif _CNPJ_FILE.exists():
            source = _CNPJ_FILE
        else:
            return None

        df = pd.read_excel(source, engine="openpyxl")

        # Garantir que as colunas necessárias existam
        available_name_cols = [c for c in _NAME_COLS if c in df.columns]
        if _CNPJ_COL not in df.columns or not available_name_cols:
            return None

        keep = available_name_cols + [_CNPJ_COL]
        df = df[keep].copy()

        # Criar colunas normalizadas para lookup rápido
        for col in available_name_cols:
            df[f"_norm_{col}"] = df[col].apply(_normalize)

        return df

    except Exception:
        return None


def lookup_cnpj(supplier: str, cnpj_db: pd.DataFrame) -> str:
    """
    Busca o CNPJ de um fornecedor pelo nome.
    Tenta cada coluna de nome em ordem de prioridade.
    Retorna o CNPJ formatado ou 'Não encontrado'.
    """
    if cnpj_db is None or cnpj_db.empty:
        return "Não encontrado"

    norm = _normalize(supplier)

    for col in _NAME_COLS:
        norm_col = f"_norm_{col}"
        if norm_col not in cnpj_db.columns:
            continue
        matches = cnpj_db[cnpj_db[norm_col] == norm]
        if not matches.empty:
            cnpj = str(matches.iloc[0][_CNPJ_COL]).strip()
            if cnpj and cnpj.lower() not in ("nan", "none", ""):
                return cnpj

    return "Não encontrado"


def build_cnpj_map(suppliers: list[str], cnpj_db: pd.DataFrame) -> dict[str, str]:
    """
    Constrói um mapa {nome_fornecedor: cnpj} para uma lista de fornecedores.
    Útil para enriquecer DataFrames com a coluna CNPJ.
    """
    return {s: lookup_cnpj(s, cnpj_db) for s in suppliers}
