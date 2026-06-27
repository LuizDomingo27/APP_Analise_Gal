# -*- coding: utf-8 -*-
"""
Gerenciamento do histórico de cobranças — tabela historico_cobrancas (SQLite).
"""

import io
import uuid
import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.config.settings import COLS, DB_PATH, DATASET_DIR
from src.data.database import create_tables, get_connection
from src.data.github_sync import push_db_to_github

# ── Legado: mantido para imports externos que ainda referenciam este caminho ──
_BASE_DIR   = Path(__file__).resolve().parents[2]
BD_COBRANCA = DATASET_DIR / "bd_cobranca.xlsx"   # usado apenas como referência de nome

# ── Valores válidos de status ─────────────────────────────────────────────────
STATUS_OPTIONS = ["Pendente", "Pago", "Contestado"]
STATUS_DEFAULT = "Pendente"

# ── Paleta ────────────────────────────────────────────────────────────────────
_PURPLE_DARK  = "1A1530"
_PURPLE_MID   = "534AB7"
_PURPLE_LIGHT = "EDE8FF"
_WHITE        = "FFFFFF"
_GRAY_BORDER  = "C8C0F0"
_TEXT_LIGHT   = "C8C0F0"

_STATUS_COLORS = {
    "Pago":       {"bg": "1D9E75", "fg": "FFFFFF"},
    "Pendente":   {"bg": "EF9F27", "fg": "1A1530"},
    "Contestado": {"bg": "D85A30", "fg": "FFFFFF"},
}

_HEADER_OFFSET = 4

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

HISTORY_LABELS = {
    COLS["order"]:     "OM",
    COLS["date"]:      "Data Produção",
    COLS["supplier"]:  "Fornecedor",
    COLS["quantity"]:  "Qtd",
    COLS["defect"]:    "Remonte",
    COLS["real_cut"]:  "Real Cortado",
    COLS["minutes"]:   "Min. Gerados",
    COLS["value_brl"]: "Valor (R$)",
    "COD_LANCAMENTO":  "Código",
    "DATA_COBRANCA":   "Data Cobrança",
    "DATA_VENCIMENTO": "Data Vencimento",
    "DATA_PAGAMENTO":  "Data Pagamento",
    "CNPJ_FORNECEDOR": "CNPJ",
    COLS["status"]:    "Status",
}

_COL_WIDTHS = {
    "COD_LANCAMENTO":                   16,
    "DATA_COBRANCA":                    14,
    "DATA_VENCIMENTO":                  14,
    "DATA_PAGAMENTO":                   14,
    "CNPJ_FORNECEDOR":                  22,
    COLS["status"]:                     16,
    COLS["order"]:                      16,
    COLS["date"]:                       16,
    COLS["supplier"]:                   34,
    COLS["quantity"]:                   12,
    COLS["defect"]:                     26,
    COLS["real_cut"]:                   14,
    COLS["minutes"]:                    16,
    COLS["value_brl"]:                  20,
}


def payment_punctuality(data_pagamento, data_vencimento) -> tuple[int | None, bool | None]:
    """
    Compara Data Pagamento × Data Vencimento.
    Retorna (dias_de_atraso, atrasado):
      dias > 0  → pago com atraso
      dias <= 0 → no prazo
      (None, None) → faltam dados
    """
    venc = pd.to_datetime(data_vencimento, format="%d/%m/%Y", errors="coerce") \
        if isinstance(data_vencimento, str) else pd.to_datetime(data_vencimento, errors="coerce")
    pag = pd.to_datetime(data_pagamento, format="%d/%m/%Y", errors="coerce") \
        if isinstance(data_pagamento, str) else pd.to_datetime(data_pagamento, errors="coerce")

    if pag is None or pd.isna(pag) or venc is None or pd.isna(venc):
        return None, None

    dias = (pag.date() - venc.date()).days
    return dias, dias > 0


def gerar_cod_lancamento() -> str:
    return f"PAG-{uuid.uuid4().hex[:8].upper()}"


def _cod_lancamento_fallback(cnpj: str, data_cobranca: str) -> str:
    chave = f"{cnpj}|{data_cobranca}".encode("utf-8")
    return "LEG-" + hashlib.md5(chave).hexdigest()[:8].upper()


# ── Público: escrita ──────────────────────────────────────────────────────────

def save_charge_to_history(
    supplier: str,
    cnpj: str,
    total: float,
    df_records: pd.DataFrame,
    display_cols: list[str],
    data_cobranca: date,
    data_vencimento: date,
) -> str:
    """
    Persiste os registros da cobrança na tabela historico_cobrancas (SQLite).
    Retorna o COD_LANCAMENTO gerado.
    """
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    create_tables()

    data_cobranca_br   = data_cobranca.strftime("%d/%m/%Y")
    data_vencimento_br = data_vencimento.strftime("%d/%m/%Y")
    cod_lancamento     = gerar_cod_lancamento()

    cols_to_save = [c for c in _SAVE_COLS if c in df_records.columns]
    df_save = df_records[cols_to_save].copy()

    for col in df_save.columns:
        if pd.api.types.is_datetime64_any_dtype(df_save[col]):
            df_save[col] = df_save[col].dt.strftime("%d/%m/%Y")

    df_save.insert(0, "COD_LANCAMENTO",  cod_lancamento)
    df_save.insert(1, "DATA_COBRANCA",   data_cobranca_br)
    df_save.insert(2, "DATA_VENCIMENTO", data_vencimento_br)
    df_save.insert(3, "DATA_PAGAMENTO",  "")
    df_save.insert(4, "CNPJ_FORNECEDOR", cnpj)
    df_save.insert(5, COLS["status"],    STATUS_DEFAULT)

    with get_connection() as conn:
        df_save.to_sql("historico_cobrancas", conn, if_exists="append", index=False)
        conn.commit()

    st.cache_data.clear()
    push_db_to_github(DB_PATH)
    return cod_lancamento


def update_lancamento_status(
    cod_lancamento: str,
    novo_status: str,
    data_pagamento: date | None = None,
) -> bool:
    """
    Atualiza o status de todos os itens de um lançamento.
    Quando novo_status == "Pago": move atomicamente para pagamentos_concluidos.
    """
    if novo_status not in STATUS_OPTIONS:
        return False

    create_tables()

    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT COUNT(*) FROM historico_cobrancas WHERE COD_LANCAMENTO = ?",
                (cod_lancamento,),
            ).fetchone()
            if not rows or rows[0] == 0:
                return False

            if novo_status == "Pago":
                data_pagamento_br = data_pagamento.strftime("%d/%m/%Y") if data_pagamento else ""

                df_pago = pd.read_sql(
                    "SELECT * FROM historico_cobrancas WHERE COD_LANCAMENTO = ?",
                    conn,
                    params=(cod_lancamento,),
                )
                df_pago[COLS["status"]]  = "Pago"
                df_pago["DATA_PAGAMENTO"] = data_pagamento_br

                df_pago.to_sql("pagamentos_concluidos", conn, if_exists="append", index=False)
                conn.execute(
                    "DELETE FROM historico_cobrancas WHERE COD_LANCAMENTO = ?",
                    (cod_lancamento,),
                )
            else:
                conn.execute(
                    "UPDATE historico_cobrancas SET STATUS_COBRANCA = ?, DATA_PAGAMENTO = '' "
                    "WHERE COD_LANCAMENTO = ?",
                    (novo_status, cod_lancamento),
                )

            conn.commit()

        st.cache_data.clear()
        push_db_to_github(DB_PATH)
        return True

    except Exception:
        return False


def migrate_paid_to_payments() -> int:
    """
    Move lançamentos com STATUS='Pago' que porventura ainda estejam em
    historico_cobrancas para pagamentos_concluidos. Idempotente.
    """
    create_tables()

    with get_connection() as conn:
        df_pago = pd.read_sql(
            "SELECT * FROM historico_cobrancas WHERE STATUS_COBRANCA = 'Pago'",
            conn,
        )
        if df_pago.empty:
            return 0

        df_pago.to_sql("pagamentos_concluidos", conn, if_exists="append", index=False)
        conn.execute(
            "DELETE FROM historico_cobrancas WHERE STATUS_COBRANCA = 'Pago'"
        )
        conn.commit()

    count = len(df_pago)
    st.cache_data.clear()
    push_db_to_github(DB_PATH)
    return count


def remove_supplier_from_df(supplier: str, supplier_col: str) -> None:
    """
    Remove todos os registros do fornecedor da tabela registros_defeitos
    e atualiza o session_state.
    """
    if "df" not in st.session_state:
        return

    df_atual    = st.session_state["df"]
    df_filtrado = df_atual[df_atual[supplier_col] != supplier].copy()
    df_filtrado.reset_index(drop=True, inplace=True)
    st.session_state["df"] = df_filtrado

    try:
        create_tables()
        with get_connection() as conn:
            conn.execute(
                'DELETE FROM registros_defeitos WHERE "FORNECEDOR" = ?',
                (supplier,),
            )
            conn.commit()
        push_db_to_github(DB_PATH)
    except Exception as exc:
        st.warning(f"⚠️ Não foi possível remover do banco: {exc}")
        return

    from src.data.loader import load_data_from_disk
    load_data_from_disk.clear()


# ── Público: leitura ──────────────────────────────────────────────────────────

@st.cache_data
def load_history() -> pd.DataFrame | None:
    """Carrega o histórico completo de historico_cobrancas. Retorna None se vazio."""
    if not DB_PATH.exists():
        return None
    create_tables()
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM historico_cobrancas", conn)
    if df.empty:
        return None
    df["DATA_PAGAMENTO"] = df["DATA_PAGAMENTO"].fillna("").astype(str).replace(
        {"nan": "", "None": "", "NaT": ""}
    )
    return df


# ── Público: geração de xlsx para download ────────────────────────────────────

def generate_history_xlsx_bytes() -> bytes | None:
    """
    Gera o xlsx formatado do histórico de cobranças em memória e retorna os bytes.
    Retorna None se não houver dados.
    """
    if not DB_PATH.exists():
        return None
    create_tables()
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM historico_cobrancas", conn)
    if df.empty:
        return None
    df["DATA_PAGAMENTO"] = df["DATA_PAGAMENTO"].fillna("").astype(str).replace(
        {"nan": "", "None": "", "NaT": ""}
    )
    buf = io.BytesIO()
    _write_history_xlsx(df, buf)
    return buf.getvalue()


# ── Privado: escrita xlsx ─────────────────────────────────────────────────────

def _write_history_xlsx(df: pd.DataFrame, dest) -> None:
    """
    Grava df como xlsx formatado em dest (Path ou file-like / BytesIO).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Histórico Cobranças"

    all_cols  = list(df.columns)
    num_cols  = len(all_cols)
    last_col  = get_column_letter(num_cols)
    today_br  = date.today().strftime("%d/%m/%Y")
    n_records = len(df)

    def thin(color=_GRAY_BORDER):
        s = Side(style="thin", color=color)
        return Border(left=s, right=s, top=s, bottom=s)

    def header_border():
        thick = Side(style="medium", color=_PURPLE_MID)
        thin_ = Side(style="thin",   color=_PURPLE_MID)
        return Border(left=thin_, right=thin_, top=thick, bottom=thick)

    ws.merge_cells(f"A1:{last_col}1")
    c = ws["A1"]
    c.value     = "HISTÓRICO DE COBRANÇAS — DEFEITOS / REMONTES"
    c.font      = Font(name="Calibri", bold=True, size=15, color=_WHITE)
    c.fill      = PatternFill("solid", fgColor=_PURPLE_DARK)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    ws.merge_cells(f"A2:{last_col}2")
    c = ws["A2"]
    c.value     = f"Gerado em: {today_br}  ·  Total de registros: {n_records}"
    c.font      = Font(name="Calibri", size=10, color=_TEXT_LIGHT)
    c.fill      = PatternFill("solid", fgColor=_PURPLE_DARK)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    ws.row_dimensions[3].height = 6

    header_row = _HEADER_OFFSET
    col_labels = {
        "COD_LANCAMENTO":  "Código",
        "DATA_COBRANCA":   "Data Cobrança",
        "DATA_VENCIMENTO": "Data Vencimento",
        "DATA_PAGAMENTO":  "Data Pagamento",
        "CNPJ_FORNECEDOR": "CNPJ",
        COLS["status"]:    "Status",
        COLS["order"]:     "OM",
        COLS["date"]:      "Data Produção",
        COLS["supplier"]:  "Fornecedor",
        COLS["quantity"]:  "Qtd",
        COLS["defect"]:    "Remonte / Defeito",
        COLS["real_cut"]:  "Real Cortado",
        COLS["minutes"]:   "Min. Gerados",
        COLS["value_brl"]: "Valor (R$)",
    }
    for idx, col in enumerate(all_cols, start=1):
        cell = ws.cell(row=header_row, column=idx)
        cell.value     = col_labels.get(col, col)
        cell.font      = Font(name="Calibri", bold=True, size=10, color=_WHITE)
        cell.fill      = PatternFill("solid", fgColor=_PURPLE_MID)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = header_border()
    ws.row_dimensions[header_row].height = 26

    value_col_name  = COLS["value_brl"]
    status_col_name = COLS["status"]
    total_value     = 0.0

    for row_idx, (_, row) in enumerate(df.iterrows(), start=header_row + 1):
        fill_color = _PURPLE_LIGHT if row_idx % 2 == 0 else _WHITE

        for col_idx, col in enumerate(all_cols, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = thin()

            val = row.get(col)
            if pd.isna(val):
                val = ""

            if col == status_col_name:
                status_val = str(val) if val != "" else STATUS_DEFAULT
                colors     = _STATUS_COLORS.get(status_val, {"bg": _PURPLE_LIGHT, "fg": "1A1530"})
                cell.value     = status_val
                cell.fill      = PatternFill("solid", fgColor=colors["bg"])
                cell.font      = Font(name="Calibri", size=9, bold=True, color=colors["fg"])
                cell.alignment = Alignment(horizontal="center", vertical="center")
                continue

            if col == value_col_name:
                fval = float(val) if val != "" else 0.0
                total_value       += fval
                cell.value         = fval
                cell.number_format = 'R$ #,##0.00'
                cell.fill          = PatternFill("solid", fgColor=fill_color)
                cell.alignment     = Alignment(horizontal="right")
                cell.font          = Font(name="Calibri", size=9, color="1A1530")
                continue

            cell.fill = PatternFill("solid", fgColor=fill_color)
            cell.font = Font(name="Calibri", size=9)

            if col == "COD_LANCAMENTO":
                cell.font      = Font(name="Consolas", size=9, bold=True, color=_PURPLE_MID)
                cell.alignment = Alignment(horizontal="center")
            elif col == "DATA_VENCIMENTO":
                cell.alignment = Alignment(horizontal="center")
                _venc_dt = pd.to_datetime(val, format="%d/%m/%Y", errors="coerce") if val else None
                _status_atual = str(row.get(status_col_name, "")).strip()
                if (
                    _venc_dt is not None and not pd.isna(_venc_dt)
                    and _venc_dt.date() < date.today()
                    and _status_atual != "Pago"
                ):
                    cell.font = Font(name="Calibri", size=9, bold=True, color="C0392B")
            elif col == "DATA_PAGAMENTO":
                cell.alignment = Alignment(horizontal="center")
                _status_atual = str(row.get(status_col_name, "")).strip()
                if _status_atual == "Pago" and not val:
                    cell.value = ""
                    cell.fill  = PatternFill("solid", fgColor="FBE8C8")
                    cell.font  = Font(name="Calibri", size=9, italic=True, color="9A6B1E")
                elif _status_atual == "Pago" and val:
                    _dias_atraso, _atrasado = payment_punctuality(val, row.get("DATA_VENCIMENTO"))
                    if _atrasado:
                        cell.font = Font(name="Calibri", size=9, bold=True, color="C0392B")
                    elif _atrasado is False:
                        cell.font = Font(name="Calibri", size=9, bold=True, color="1D9E75")
            elif col in ("DATA_COBRANCA", COLS["date"]):
                cell.alignment = Alignment(horizontal="center")
            elif col == "CNPJ_FORNECEDOR":
                cell.font      = Font(name="Calibri", size=9, color="1D9E75", bold=True)
                cell.alignment = Alignment(horizontal="center")
            elif col in (COLS["quantity"], COLS["real_cut"], COLS["minutes"]):
                cell.alignment = Alignment(horizontal="center")
            elif col == COLS["order"]:
                cell.font      = Font(name="Calibri", size=9, bold=True)
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")

            cell.value = val

        ws.row_dimensions[row_idx].height = 17

    total_row   = header_row + n_records + 1
    val_col_idx = (all_cols.index(value_col_name) + 1 if value_col_name in all_cols else num_cols)
    merge_end   = get_column_letter(val_col_idx - 1)
    _RED = "C0392B"

    ws.merge_cells(f"A{total_row}:{merge_end}{total_row}")
    lc = ws[f"A{total_row}"]
    lc.value     = "TOTAL HISTÓRICO"
    lc.font      = Font(name="Calibri", bold=True, size=10, color=_WHITE)
    lc.fill      = PatternFill("solid", fgColor=_RED)
    lc.alignment = Alignment(horizontal="right", vertical="center")
    lc.border    = thin(_RED)

    tc = ws.cell(row=total_row, column=val_col_idx)
    tc.value         = total_value
    tc.number_format = 'R$ #,##0.00'
    tc.font          = Font(name="Calibri", bold=True, size=11, color=_WHITE)
    tc.fill          = PatternFill("solid", fgColor=_RED)
    tc.alignment     = Alignment(horizontal="right", vertical="center")
    tc.border        = thin(_RED)
    ws.row_dimensions[total_row].height = 22

    for col_idx in range(val_col_idx + 1, num_cols + 1):
        c = ws.cell(row=total_row, column=col_idx)
        c.fill   = PatternFill("solid", fgColor=_RED)
        c.border = thin(_RED)

    footer_row = total_row + 2
    ws.merge_cells(f"A{footer_row}:{last_col}{footer_row}")
    c = ws[f"A{footer_row}"]
    c.value = (
        "Documento gerado automaticamente pelo sistema de Controle de Qualidade. "
        "Este histórico acumula todas as cobranças confirmadas no período."
    )
    c.font      = Font(name="Calibri", italic=True, size=8, color="888888")
    c.alignment = Alignment(horizontal="center", wrap_text=True)
    ws.row_dimensions[footer_row].height = 28

    for idx, col in enumerate(all_cols, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = _COL_WIDTHS.get(col, 16)

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    wb.save(dest)
