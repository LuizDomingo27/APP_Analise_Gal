"""
Script de migração one-time: importa os 3 xlsx existentes para o SQLite.

Execute localmente UMA VEZ, antes do primeiro deploy com SQLite:
    python migrate_excel.py

Depois comite o arquivo dataset/analise_gal.db gerado.
"""

import re as _re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config.settings import DATASET_DIR, COLS
from src.data.database import create_tables, get_connection

BD_PRINCIPAL  = DATASET_DIR / "bd_principal.xlsx"
BD_COBRANCA   = DATASET_DIR / "bd_cobranca.xlsx"
BD_PAGAMENTOS = DATASET_DIR / "bd_pagamentos.xlsx"

_SAVE_COLS = [
    COLS["order"],
    COLS["date"],
    COLS["supplier"],
    COLS["quantity"],
    COLS["defect"],
    COLS["real_cut"],
    COLS["minutes"],
    COLS["value_brl"],
]

_LABEL_TO_INTERNAL = {
    "Código":                  "COD_LANCAMENTO",
    "Codigo":                  "COD_LANCAMENTO",
    "Código do Pagamento":     "COD_LANCAMENTO",
    "COD_LANCAMENTO":          "COD_LANCAMENTO",
    "Data Cobranca":           "DATA_COBRANCA",
    "Data Cobrança":           "DATA_COBRANCA",
    "Data Vencimento":         "DATA_VENCIMENTO",
    "Vencimento":              "DATA_VENCIMENTO",
    "Data Pagamento":          "DATA_PAGAMENTO",
    "Data de Pagamento":       "DATA_PAGAMENTO",
    "CNPJ":                    "CNPJ_FORNECEDOR",
    "Status":                  COLS["status"],
    "STATUS_COBRANCA":         COLS["status"],
    "OM":                      COLS["order"],
    "Data Prodção":            COLS["date"],
    "Data Producao":           COLS["date"],
    "Data Produção":           COLS["date"],
    "Fornecedor":              COLS["supplier"],
    "Qtd":                     COLS["quantity"],
    "Remonte / Defeito":       COLS["defect"],
    "Real Cortado":            COLS["real_cut"],
    "Min. Gerados":            COLS["minutes"],
    "Valor (R$)":              COLS["value_brl"],
}


def _read_cobranca_xlsx(path: Path, header_offset: int) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl", header=header_offset - 1)
    _date_pat = _re.compile(r"^\d{2}/\d{2}/\d{4}$")
    _matches  = [c for c in df.columns if str(c).strip() in ("Data Cobrança", "Data Cobranca")]
    filter_col = _matches[0] if _matches else df.columns[0]
    df = df[df[filter_col].astype(str).str.match(_date_pat)].reset_index(drop=True)
    df = df.rename(columns=_LABEL_TO_INTERNAL)
    df = df.loc[:, ~df.columns.str.contains(r"\.\d+$", regex=True)]
    return df


def migrate_principal() -> int:
    if not BD_PRINCIPAL.exists():
        print(f"  [SKIP] {BD_PRINCIPAL.name} não encontrado.")
        return 0
    df = pd.read_excel(BD_PRINCIPAL, engine="openpyxl")
    df[COLS["date"]] = pd.to_datetime(df[COLS["date"]], errors="coerce").dt.strftime("%Y-%m-%d")
    df.dropna(subset=[COLS["date"]], inplace=True)
    with get_connection() as conn:
        df.to_sql("registros_defeitos", conn, if_exists="append", index=False)
        conn.commit()
    return len(df)


def migrate_cobranca() -> int:
    if not BD_COBRANCA.exists():
        print(f"  [SKIP] {BD_COBRANCA.name} não encontrado.")
        return 0
    df = _read_cobranca_xlsx(BD_COBRANCA, header_offset=4)
    if "DATA_PAGAMENTO" not in df.columns:
        df["DATA_PAGAMENTO"] = ""
    df["DATA_PAGAMENTO"] = df["DATA_PAGAMENTO"].fillna("").astype(str).replace(
        {"nan": "", "None": "", "NaT": ""}
    )
    if "DATA_VENCIMENTO" not in df.columns:
        df["DATA_VENCIMENTO"] = ""
    if COLS["status"] not in df.columns:
        df[COLS["status"]] = "Pendente"
    with get_connection() as conn:
        df.to_sql("historico_cobrancas", conn, if_exists="append", index=False)
        conn.commit()
    return len(df)


def migrate_pagamentos() -> int:
    if not BD_PAGAMENTOS.exists():
        print(f"  [SKIP] {BD_PAGAMENTOS.name} não encontrado.")
        return 0
    df = _read_cobranca_xlsx(BD_PAGAMENTOS, header_offset=5)
    if "DATA_PAGAMENTO" not in df.columns:
        df["DATA_PAGAMENTO"] = ""
    df["DATA_PAGAMENTO"] = df["DATA_PAGAMENTO"].fillna("").astype(str).replace(
        {"nan": "", "None": "", "NaT": ""}
    )
    if COLS["status"] not in df.columns:
        df[COLS["status"]] = "Pago"
    with get_connection() as conn:
        df.to_sql("pagamentos_concluidos", conn, if_exists="append", index=False)
        conn.commit()
    return len(df)


def main() -> None:
    print("Criando tabelas SQLite...")
    create_tables()

    print("Migrando bd_principal.xlsx -> registros_defeitos...")
    n = migrate_principal()
    print(f"  OK {n} registros inseridos.")

    print("Migrando bd_cobranca.xlsx -> historico_cobrancas...")
    n = migrate_cobranca()
    print(f"  OK {n} registros inseridos.")

    print("Migrando bd_pagamentos.xlsx -> pagamentos_concluidos...")
    n = migrate_pagamentos()
    print(f"  OK {n} registros inseridos.")

    from src.config.settings import DB_PATH
    print(f"\nBanco criado em: {DB_PATH}")
    print("Próximo passo: git add dataset/analise_gal.db && git commit && git push")


if __name__ == "__main__":
    main()
