# -*- coding: utf-8 -*-
"""
UI da página de Correção de Registros — módulo isolado.

Afeta exclusivamente registros_defeitos (nunca historico_cobrancas ou
pagamentos_concluidos). Duas ferramentas:
  1. Unificar Valores  — find & replace em massa numa coluna de texto
     (ex.: fornecedor com/sem acento, caractere especial).
  2. Editar Registros  — busca + tabela + painel "selecionar e salvar",
     no mesmo layout usado em Histórico de Cobranças / Pagamentos Concluídos.
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.config.settings import COLS, COLORS
from src.data.records_editor import (
    EDITABLE_TEXT_COLUMNS,
    get_distinct_suppliers,
    get_value_counts,
    rename_value,
    search_records,
    update_record_fields,
)

_TEXT_COL_LABELS = {
    COLS["supplier"]: "Fornecedor",
    COLS["material"]: "Material",
    COLS["location"]: "Local",
    COLS["defect"]:   "Remonte / Tipo de Defeito",
}

_EDIT_DISPLAY_COLS = [
    COLS["date"],
    COLS["order"],
    COLS["material"],
    COLS["supplier"],
    COLS["quantity"],
    COLS["location"],
    COLS["defect"],
    COLS["real_cut"],
    COLS["minutes"],
    COLS["value_brl"],
]

_EDIT_COL_LABELS = {
    COLS["date"]:       "Data",
    COLS["order"]:      "OM",
    COLS["material"]:   "Material",
    COLS["supplier"]:   "Fornecedor",
    COLS["quantity"]:   "Qtd",
    COLS["location"]:   "Local",
    COLS["defect"]:     "Remonte",
    COLS["real_cut"]:   "Rel. Cortado",
    COLS["minutes"]:    "Min. Gerados",
    COLS["value_brl"]:  "Valor (R$)",
}

_LEFT_ALIGN_LABELS = {"Fornecedor", "Material", "Local", "Remonte", "Remonte / Tipo de Defeito"}


def render_records_editor_page() -> None:
    _render_header()

    tab_unify, tab_edit = st.tabs(["🔤 Unificar Valores", "📝 Editar Registros"])

    with tab_unify:
        _render_unify_tab()

    with tab_edit:
        _render_individual_edit_tab()


# ══════════════════════════════════════════════════════════════════════════════
# Tabela HTML padrão — mesmo layout de Histórico de Cobranças / Pagamentos
# ══════════════════════════════════════════════════════════════════════════════

def _render_html_table(df_display: pd.DataFrame, height: int = 400, min_width: int = 0) -> None:
    headers = list(df_display.columns)
    min_width_css = f"min-width:{min_width}px;" if min_width else ""

    TH = (
        "padding:11px 14px;text-align:center;color:#FFFFFF;font-weight:600;"
        "font-size:11px;text-transform:uppercase;letter-spacing:0.7px;"
        "background:#00805C;border-bottom:2px solid #00B884;"
        "white-space:nowrap;position:sticky;top:0;z-index:1;"
    )
    TH_L = TH + "text-align:left;"

    head_html = "".join(
        f'<th style="{TH_L if h in _LEFT_ALIGN_LABELS else TH}">✦ {h}</th>'
        for h in headers
    )

    def _make_cell(h, val, row_bg):
        is_left = h in _LEFT_ALIGN_LABELS
        align = "text-align:left;" if is_left else "text-align:center;"
        base_td = (
            f"padding:9px 14px;font-size:12.5px;color:#0D1B17;"
            f"border-bottom:1px solid rgba(0,229,160,0.12);"
            f"{align}{row_bg}"
        )
        if h in ("Valor (R$)", "Valor do Processo (R$)"):
            return (
                f'<td style="{base_td}">'
                f'<span style="background:#00B884;color:#FFFFFF;'
                f'padding:3px 9px;border-radius:6px;'
                f'font-size:12px;font-weight:600;white-space:nowrap;">'
                f'{val}</span></td>'
            )
        return f'<td style="{base_td}">{val}</td>'

    rows_html = "".join(
        f"<tr>" + "".join(_make_cell(h, row[h], "background:#FFFFFF;" if i % 2 == 1 else "background:#F2F7F5;") for h in headers) + "</tr>"
        for i, (_, row) in enumerate(df_display.iterrows())
    )

    table_html = f"""
    <style>
      .nv-table-wrap::-webkit-scrollbar {{ width:6px; height:6px; }}
      .nv-table-wrap::-webkit-scrollbar-track {{ background:#FFFFFF; border-radius:3px; }}
      .nv-table-wrap::-webkit-scrollbar-thumb {{ background:rgba(0,229,160,0.45); border-radius:3px; }}
      .nv-table-wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(0,229,160,0.70); }}
      .nv-table-wrap tr:hover td {{ background:rgba(0,229,160,0.14)!important; transition:background 0.15s; }}
    </style>
    <div class="nv-table-wrap" style="
        max-height:{height}px; overflow:auto; border-radius:12px;
        border:1px solid rgba(0,229,160,0.32);
        border-top:2px solid #00B884;
        background:#F2F7F5;
        box-shadow:0 0 22px rgba(0,229,160,0.10);
    ">
      <table style="width:100%;border-collapse:collapse;{min_width_css}">
        <thead><tr>{head_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════════════

def _render_header() -> None:
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(0,0,0,0.06);margin-bottom:1.2rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">
                    🛠️ Correção de Registros
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(0,229,160,0.18);
                             padding:3px 10px;border-radius:20px;
                             border:1px solid rgba(0,229,160,0.3)">
                    Base Ativa
                </span>
            </div>
            <p style="color:{COLORS['text_muted']};font-size:13px;margin:5px 0 0">
                Corrija valores digitados incorretamente (acentos, caracteres
                especiais, variações de nome). Afeta apenas a tabela
                <code style="background:rgba(0,229,160,0.12);padding:1px 6px;border-radius:4px">
                    registros_defeitos
                </code>
                — histórico e pagamentos de cobrança não são alterados.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Unificar Valores (find & replace em massa)
# ══════════════════════════════════════════════════════════════════════════════

def _render_unify_tab() -> None:
    st.markdown(
        f"""
        <p style="font-size:12.5px;color:{COLORS['text_muted']};margin:4px 0 14px;line-height:1.6">
            Escolha uma coluna de texto, veja os valores distintos hoje cadastrados
            e corrija um valor errado (ex.: <code>FORNECEDOR LTDA</code> vs
            <code>FORNECEDOR LTDA</code> com acento diferente). A correção é
            aplicada a <strong>todos</strong> os registros com o valor selecionado.
        </p>
        """,
        unsafe_allow_html=True,
    )

    column = st.selectbox(
        "Coluna a corrigir",
        options=EDITABLE_TEXT_COLUMNS,
        format_func=lambda c: _TEXT_COL_LABELS.get(c, c),
        key="unify_column_select",
    )

    df_values = get_value_counts(column)
    if df_values.empty:
        st.info("Nenhum registro encontrado para esta coluna.")
        return

    col_label = _TEXT_COL_LABELS.get(column, column)
    df_display = df_values.rename(columns={"valor": col_label, "qtd": "Registros"})
    df_display["Registros"] = df_display["Registros"].apply(lambda v: f"{int(v):,}")

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    _render_html_table(df_display, height=min(340, 50 + 38 * len(df_display)))

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    value_options = df_values["valor"].tolist()
    col_old, col_new = st.columns(2)

    with col_old:
        old_value = st.selectbox(
            "Valor a corrigir (atual)",
            options=value_options,
            format_func=lambda v: f"{v}  —  {int(df_values.loc[df_values['valor'] == v, 'qtd'].iloc[0]):,} registro(s)",
            key="unify_old_value",
        )

    with col_new:
        new_value = st.text_input(
            "Novo valor (correto)",
            value=old_value,
            key="unify_new_value",
            help="Edite o texto acima para a grafia correta (acentos, "
                 "caracteres especiais etc.) e confirme abaixo.",
        )

    affected = int(df_values.loc[df_values["valor"] == old_value, "qtd"].iloc[0]) if old_value in value_options else 0

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    disabled = (not new_value or not new_value.strip() or new_value == old_value)
    if st.button(
        f"✅ Aplicar correção a {affected:,} registro(s)",
        type="primary",
        disabled=disabled,
        key="unify_apply_btn",
    ):
        with st.spinner("Atualizando registros…"):
            n = rename_value(column, old_value, new_value.strip())
        if n:
            st.success(f"✅ {n:,} registro(s) atualizado(s): \"{old_value}\" → \"{new_value.strip()}\".")
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("Nenhum registro foi alterado.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Editar Registros (tabela + painel "selecionar e salvar")
# ══════════════════════════════════════════════════════════════════════════════

def _render_individual_edit_tab() -> None:
    st.markdown(
        f"""
        <p style="font-size:12.5px;color:{COLORS['text_muted']};margin:4px 0 14px;line-height:1.6">
            Busque registros específicos, selecione um na lista abaixo da
            tabela e corrija os campos necessários no painel de edição.
        </p>
        """,
        unsafe_allow_html=True,
    )

    suppliers = get_distinct_suppliers()

    col_sup, col_om, col_dates = st.columns([2, 1, 2])
    with col_sup:
        supplier_filter = st.selectbox(
            "Fornecedor",
            options=["Todos"] + suppliers,
            key="edit_search_supplier",
        )
    with col_om:
        order_filter = st.text_input(
            "OM (parcial)",
            key="edit_search_order",
            placeholder="ex.: 30026",
        )
    with col_dates:
        date_range = st.date_input(
            "Período",
            value=(date.today() - timedelta(days=30), date.today()),
            format="DD/MM/YYYY",
            key="edit_search_dates",
        )

    date_from = date_range[0] if isinstance(date_range, tuple) and len(date_range) >= 1 else None
    date_to   = date_range[1] if isinstance(date_range, tuple) and len(date_range) >= 2 else date_from

    df_results = search_records(
        supplier=None if supplier_filter == "Todos" else supplier_filter,
        date_from=date_from,
        date_to=date_to,
        order=order_filter.strip() if order_filter else None,
    )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if df_results.empty:
        st.info("Nenhum registro encontrado com os filtros informados.")
        return

    df_view = df_results[_EDIT_DISPLAY_COLS].copy()
    df_view[COLS["date"]] = df_view[COLS["date"]].dt.strftime("%d/%m/%Y")
    df_view = df_view.rename(columns=_EDIT_COL_LABELS)
    df_view["Qtd"] = df_view["Qtd"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "")
    df_view["Min. Gerados"] = df_view["Min. Gerados"].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")
    df_view["Valor (R$)"] = df_view["Valor (R$)"].apply(lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else "")

    _render_html_table(df_view, height=min(460, 50 + 38 * len(df_view)), min_width=980)

    st.markdown(
        f"<p style='font-size:11px;color:{COLORS['text_subtle']};margin-top:6px'>"
        f"{len(df_results):,} registro(s) exibido(s)"
        f"{' (limitado às 500 primeiras linhas)' if len(df_results) >= 500 else ''}."
        f"</p>",
        unsafe_allow_html=True,
    )

    # ── Painel de Edição — mesmo layout de "Atualizar Status de Lançamento" ──
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.expander("📝 Editar Registro Selecionado", expanded=True):
        record_opts = [
            (
                f"OM {row[COLS['order']]} — {row[COLS['supplier']]} — "
                f"{row[COLS['date']].strftime('%d/%m/%Y')} — R$ {row[COLS['value_brl']]:,.2f}",
                int(row["_rowid"]),
            )
            for _, row in df_results.iterrows()
        ]

        selected_label, selected_rowid = st.selectbox(
            "Selecionar Registro",
            options=record_opts,
            format_func=lambda x: x[0],
            key="select_record_to_edit",
        )

        record = df_results.loc[df_results["_rowid"] == selected_rowid].iloc[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            new_supplier = st.text_input(
                "Fornecedor", value=str(record[COLS["supplier"]]), key=f"edit_supplier_{selected_rowid}"
            )
            new_material = st.text_input(
                "Material", value=str(record[COLS["material"]]), key=f"edit_material_{selected_rowid}"
            )
        with col2:
            new_location = st.text_input(
                "Local", value=str(record[COLS["location"]]), key=f"edit_location_{selected_rowid}"
            )
            new_defect = st.text_input(
                "Remonte / Tipo de Defeito", value=str(record[COLS["defect"]]), key=f"edit_defect_{selected_rowid}"
            )
        with col3:
            new_order = st.text_input(
                "OM", value=str(record[COLS["order"]]), key=f"edit_order_{selected_rowid}"
            )
            new_date = st.date_input(
                "Data de Produção",
                value=record[COLS["date"]].date(),
                format="DD/MM/YYYY",
                key=f"edit_date_{selected_rowid}",
            )

        col4, col5, col6, col7 = st.columns(4)
        with col4:
            new_qty = st.number_input(
                "Qtd", value=int(record[COLS["quantity"]]), min_value=0, step=1, key=f"edit_qty_{selected_rowid}"
            )
        with col5:
            new_real_cut = st.text_input(
                "Rel. Cortado", value=str(record[COLS["real_cut"]]), key=f"edit_realcut_{selected_rowid}"
            )
        with col6:
            new_minutes = st.number_input(
                "Min. Gerados", value=float(record[COLS["minutes"]]), min_value=0.0, step=0.1,
                format="%.2f", key=f"edit_minutes_{selected_rowid}",
            )
        with col7:
            new_value_brl = st.number_input(
                "Valor (R$)", value=float(record[COLS["value_brl"]]), min_value=0.0, step=0.01,
                format="%.2f", key=f"edit_value_{selected_rowid}",
            )

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        if st.button("💾 Salvar Alteração", type="primary", key=f"edit_save_{selected_rowid}"):
            updates = {}
            if new_supplier.strip() != str(record[COLS["supplier"]]):
                updates[COLS["supplier"]] = new_supplier.strip()
            if new_material.strip() != str(record[COLS["material"]]):
                updates[COLS["material"]] = new_material.strip()
            if new_location.strip() != str(record[COLS["location"]]):
                updates[COLS["location"]] = new_location.strip()
            if new_defect.strip() != str(record[COLS["defect"]]):
                updates[COLS["defect"]] = new_defect.strip()
            if new_order.strip() != str(record[COLS["order"]]):
                updates[COLS["order"]] = new_order.strip()
            if new_date != record[COLS["date"]].date():
                updates[COLS["date"]] = new_date.strftime("%Y-%m-%d")
            if int(new_qty) != int(record[COLS["quantity"]]):
                updates[COLS["quantity"]] = int(new_qty)
            if new_real_cut.strip() != str(record[COLS["real_cut"]]):
                updates[COLS["real_cut"]] = new_real_cut.strip()
            if float(new_minutes) != float(record[COLS["minutes"]]):
                updates[COLS["minutes"]] = float(new_minutes)
            if float(new_value_brl) != float(record[COLS["value_brl"]]):
                updates[COLS["value_brl"]] = float(new_value_brl)

            if not updates:
                st.info("Nenhuma alteração detectada.")
            else:
                with st.spinner("Salvando alteração…"):
                    ok = update_record_fields(selected_rowid, updates)
                if ok:
                    st.success("✅ Registro atualizado com sucesso.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Não foi possível salvar a alteração.")
