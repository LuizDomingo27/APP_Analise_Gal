"""
Filter UI layer.
Renders the filter controls (in the main body, below the navbar) and returns
the filtered DataFrame. No chart or metric code here.
"""

import streamlit as st
import pandas as pd
from src.config.settings import COLS


def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Render the three filters (supplier, defect type, date range) in the main
    body — laid out in three columns below the navbar — and return the
    filtered DataFrame.
    """
    st.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:#4A5752;margin:0 0 8px">⚙️ Filtros</p>',
        unsafe_allow_html=True,
    )

    col_sup, col_def, col_date = st.columns(3)

    # ── Filter 1: Supplier ────────────────────────────────────────────────────
    all_suppliers = sorted(df[COLS["supplier"]].unique().tolist())
    with col_sup:
        selected_suppliers = st.multiselect(
            "🏭 Fornecedor",
            options=all_suppliers,
            default=[],
            placeholder="Todos os fornecedores",
            key="filter_supplier",
        )

    # ── Filter 2: Defect type ─────────────────────────────────────────────────
    all_defects = sorted(df[COLS["defect"]].unique().tolist())
    with col_def:
        selected_defects = st.multiselect(
            "⚠️ Tipo de Defeito",
            options=all_defects,
            default=[],
            placeholder="Todos os defeitos",
            key="filter_defect",
        )

    # ── Filter 3: Date range ──────────────────────────────────────────────────
    min_date = df[COLS["date"]].min().date()
    max_date = df[COLS["date"]].max().date()

    with col_date:
        date_range = st.date_input(
            "📅 Período",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
            key="filter_date",
        )

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = df.copy()

    if selected_suppliers:
        filtered = filtered[filtered[COLS["supplier"]].isin(selected_suppliers)]

    if selected_defects:
        filtered = filtered[filtered[COLS["defect"]].isin(selected_defects)]

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        mask = (
            (filtered[COLS["date"]].dt.date >= start)
            & (filtered[COLS["date"]].dt.date <= end)
        )
        filtered = filtered[mask]

    return filtered
