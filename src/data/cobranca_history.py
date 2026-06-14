# -*- coding: utf-8 -*-
"""
Gerenciamento do histórico de cobranças — bd_cobranca.xlsx.
"""

import io
import re as _re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.config.settings import COLS

# ── Caminho do arquivo de histórico ──────────────────────────────────────────
_BASE_DIR   = Path(__file__).resolve().parents[2]
DATASET_DIR = _BASE_DIR / "dataset"
BD_COBRANCA = DATASET_DIR / "bd_cobranca.xlsx"

# ── Valores válidos de status ─────────────────────────────────────────────────
STATUS_OPTIONS  = ["Pendente", "Pago", "Contestado"]
STATUS_DEFAULT  = "Pendente"

# ── Paleta idêntica ao charge_exporter ───────────────────────────────────────
_PURPLE_DARK  = "1A1530"
_PURPLE_MID   = "534AB7"
_PURPLE_LIGHT = "EDE8FF"
_WHITE        = "FFFFFF"
_GRAY_BORDER  = "C8C0F0"
_TEXT_LIGHT   = "C8C0F0"

# Cores de status (fundo da célula no xlsx)
_STATUS_COLORS = {
    "Pago":       {"bg": "1D9E75", "fg": "FFFFFF"},   # verde
    "Pendente":   {"bg": "EF9F27", "fg": "1A1530"},   # âmbar
    "Contestado": {"bg": "D85A30", "fg": "FFFFFF"},   # coral
}

# Número de linhas decorativas antes do header de colunas
_HEADER_OFFSET = 4   # linhas 1-2 título, 3 espaçador, 4 header de colunas

# Colunas de negócio a salvar (sem STATUS — inserido manualmente na posição 3)
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

# Rótulos amigáveis para exibição no histórico (tela)
HISTORY_LABELS = {
    COLS["order"]:     "OM",
    COLS["date"]:      "Data Produção",
    COLS["supplier"]:  "Fornecedor",
    COLS["quantity"]:  "Qtd",
    COLS["defect"]:    "Remonte",
    COLS["real_cut"]:  "Real Cortado",
    COLS["minutes"]:   "Min. Gerados",
    COLS["value_brl"]: "Valor (R$)",
    "DATA_COBRANCA":   "Data Cobrança",
    "CNPJ_FORNECEDOR": "CNPJ",
    COLS["status"]:    "Status",
}

# Larguras das colunas no xlsx
_COL_WIDTHS = {
    "DATA_COBRANCA":                    14,
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


def save_charge_to_history(
    supplier: str,
    cnpj: str,
    total: float,
    df_records: pd.DataFrame,
    display_cols: list[str],
) -> None:
    """
    Persiste os registros da cobrança em dataset/bd_cobranca.xlsx.
    Acumula sem sobrescrever cobranças anteriores.
    STATUS_COBRANCA é inserido com valor padrão "Pendente".
    """
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    today_br = date.today().strftime("%d/%m/%Y")

    cols_to_save = [c for c in _SAVE_COLS if c in df_records.columns]
    df_save = df_records[cols_to_save].copy()

    for col in df_save.columns:
        if pd.api.types.is_datetime64_any_dtype(df_save[col]):
            df_save[col] = df_save[col].dt.strftime("%d/%m/%Y")

    # Metadados de cobrança: DATA → CNPJ → STATUS (padrão Pendente)
    df_save.insert(0, "DATA_COBRANCA",   today_br)
    df_save.insert(1, "CNPJ_FORNECEDOR", cnpj)
    df_save.insert(2, COLS["status"],    STATUS_DEFAULT)

    if BD_COBRANCA.exists():
        df_existing = _read_history_xlsx()
        df_final    = pd.concat([df_existing, df_save], ignore_index=True)
    else:
        df_final = df_save

    _write_history_xlsx(df_final)
    # Limpa cache do histórico para forçar nova leitura
    st.cache_data.clear()


def update_status(row_index: int, novo_status: str) -> bool:
    """
    Atualiza o STATUS_COBRANCA de uma linha específica no bd_cobranca.xlsx.
    Retorna True em caso de sucesso, False em caso de erro.
    """
    if novo_status not in STATUS_OPTIONS:
        return False

    if not BD_COBRANCA.exists():
        return False

    try:
        wb = load_workbook(BD_COBRANCA)
        ws = wb.active

        # Linha no xlsx: _HEADER_OFFSET=4 (header na linha 4), dados começam na linha 5
        # Para row_index 0-based: xlsx_row = 4 + 1 + row_index = 5 + row_index
        xlsx_row = _HEADER_OFFSET + 1 + row_index

        # Descobrir qual coluna é STATUS_COBRANCA lendo o header (linha 4)
        status_col_idx = None
        for col_idx in range(1, ws.max_column + 1):
            cell_val = ws.cell(row=_HEADER_OFFSET, column=col_idx).value
            if cell_val in ("Status", "STATUS_COBRANCA", COLS["status"]):
                status_col_idx = col_idx
                break

        if status_col_idx is None:
            wb.close()
            return False

        cell = ws.cell(row=xlsx_row, column=status_col_idx)
        cell.value = novo_status

        # Aplicar cor de fundo condicional
        colors = _STATUS_COLORS.get(novo_status, {"bg": _PURPLE_LIGHT, "fg": "1A1530"})
        cell.fill      = PatternFill("solid", fgColor=colors["bg"])
        cell.font      = Font(name="Calibri", size=9, bold=True, color=colors["fg"])
        cell.alignment = Alignment(horizontal="center", vertical="center")

        wb.save(BD_COBRANCA)
        wb.close()
        # Limpa cache do histórico para forçar nova leitura
        st.cache_data.clear()
        return True

    except Exception:
        return False


def remove_supplier_from_df(supplier: str, supplier_col: str) -> None:
    """Remove todos os registros do fornecedor do DataFrame principal em session_state."""
    if "df" not in st.session_state:
        return
    df_atual    = st.session_state["df"]
    df_filtrado = df_atual[df_atual[supplier_col] != supplier].copy()
    df_filtrado.reset_index(drop=True, inplace=True)
    st.session_state["df"] = df_filtrado


@st.cache_data
def load_history() -> pd.DataFrame | None:
    """Carrega o histórico completo de bd_cobranca.xlsx. Retorna None se não existir."""
    if not BD_COBRANCA.exists():
        return None
    return _read_history_xlsx()


# ── Privado — leitura ─────────────────────────────────────────────────────────

def _read_history_xlsx() -> pd.DataFrame:
    """
    Lê bd_cobranca.xlsx pulando as 3 linhas decorativas do cabeçalho.
    """
    df = pd.read_excel(BD_COBRANCA, engine="openpyxl", header=3)

    _date_pat = _re.compile(r"^\d{2}/\d{2}/\d{4}$")
    first_col = df.columns[0]
    df = df[df[first_col].astype(str).str.match(_date_pat)]
    df = df.reset_index(drop=True)

    _label_to_internal = {
        "Data Cobranca":           "DATA_COBRANCA",
        "Data Cobrança":           "DATA_COBRANCA",
        "CNPJ":                    "CNPJ_FORNECEDOR",
        "Status":                  COLS["status"],
        "STATUS_COBRANCA":         COLS["status"],
        "OM":                      _SAVE_COLS[0],
        "Data Prodção":            _SAVE_COLS[1],
        "Data Producao":           _SAVE_COLS[1],
        "Data Produção":           _SAVE_COLS[1],
        "Fornecedor":              _SAVE_COLS[2],
        "Qtd":                     _SAVE_COLS[3],
        "Remonte / Defeito":       _SAVE_COLS[4],
        "Real Cortado":            _SAVE_COLS[5],
        "Min. Gerados":            _SAVE_COLS[6],
        "Valor (R$)":              _SAVE_COLS[7],
    }
    df = df.rename(columns=_label_to_internal)
    df = df.loc[:, ~df.columns.str.contains(r"\.\d+$", regex=True)]

    # Retrocompatibilidade: arquivos antigos sem STATUS_COBRANCA
    status_col = COLS["status"]
    if status_col not in df.columns:
        df.insert(2, status_col, STATUS_DEFAULT)
    else:
        df[status_col] = df[status_col].fillna(STATUS_DEFAULT)
        df[status_col] = df[status_col].astype(str).str.strip()
        # Garantir que só existam valores válidos
        df[status_col] = df[status_col].apply(
            lambda v: v if v in STATUS_OPTIONS else STATUS_DEFAULT
        )

    return df


# ── Privado — escrita ─────────────────────────────────────────────────────────

def _write_history_xlsx(df: pd.DataFrame) -> None:
    """
    Grava df em BD_COBRANCA com estilo visual.
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

    # ── Linha 1: título principal ─────────────────────────────────────────────
    ws.merge_cells(f"A1:{last_col}1")
    c = ws["A1"]
    c.value     = "HISTÓRICO DE COBRANÇAS — DEFEITOS / REMONTES"
    c.font      = Font(name="Calibri", bold=True, size=15, color=_WHITE)
    c.fill      = PatternFill("solid", fgColor=_PURPLE_DARK)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 34

    # ── Linha 2: subtítulo ────────────────────────────────────────────────────
    ws.merge_cells(f"A2:{last_col}2")
    c = ws["A2"]
    c.value     = f"Gerado em: {today_br}  ·  Total de registros: {n_records}"
    c.font      = Font(name="Calibri", size=10, color=_TEXT_LIGHT)
    c.fill      = PatternFill("solid", fgColor=_PURPLE_DARK)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    # ── Linha 3: espaçador ────────────────────────────────────────────────────
    ws.row_dimensions[3].height = 6

    # ── Linha 4: cabeçalho das colunas ───────────────────────────────────────
    header_row = _HEADER_OFFSET
    col_labels = {
        "DATA_COBRANCA":   "Data Cobrança",
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

    # ── Linhas de dados ───────────────────────────────────────────────────────
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

            # ── Coluna STATUS: cor condicional ────────────────────────────────
            if col == status_col_name:
                status_val = str(val) if val != "" else STATUS_DEFAULT
                colors     = _STATUS_COLORS.get(status_val, {"bg": _PURPLE_LIGHT, "fg": "1A1530"})
                cell.value     = status_val
                cell.fill      = PatternFill("solid", fgColor=colors["bg"])
                cell.font      = Font(name="Calibri", size=9, bold=True, color=colors["fg"])
                cell.alignment = Alignment(horizontal="center", vertical="center")
                continue

            # ── Coluna VALOR ──────────────────────────────────────────────────
            if col == value_col_name:
                fval = float(val) if val != "" else 0.0
                total_value       += fval
                cell.value         = fval
                cell.number_format = 'R$ #,##0.00'
                cell.fill          = PatternFill("solid", fgColor=fill_color)
                cell.alignment     = Alignment(horizontal="right")
                cell.font          = Font(name="Calibri", size=9, color="1A1530")
                continue

            # ── Demais colunas ────────────────────────────────────────────────
            cell.fill = PatternFill("solid", fgColor=fill_color)
            cell.font = Font(name="Calibri", size=9)

            if col in ("DATA_COBRANCA", COLS["date"]):
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

    # ── Linha de total ────────────────────────────────────────────────────────
    total_row   = header_row + n_records + 1
    val_col_idx = (all_cols.index(value_col_name) + 1
                   if value_col_name in all_cols else num_cols)
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

    # ── Rodapé ────────────────────────────────────────────────────────────────
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

    # ── Larguras de coluna ────────────────────────────────────────────────────
    for idx, col in enumerate(all_cols, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = _COL_WIDTHS.get(col, 16)

    # ── Freeze pane abaixo do cabeçalho de colunas ───────────────────────────
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    wb.save(BD_COBRANCA)
