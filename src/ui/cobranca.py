# -*- coding: utf-8 -*-
"""
UI da página de Cobrança de Fornecedores.

CHANGELOG v13:
- Refatoração arquitetural: importações atualizadas para novas camadas.
- Validação de CNPJ movida para src/utils/cnpj_validator.py.
- Exportadores movidos para src/services/.
- Histórico movido para src/data/cobranca_history.py.
"""

from datetime import date

import pandas as pd
import streamlit as st

from src.config.settings import COLS, COLORS
from src.services.charge_exporter import generate_charge_excel
from src.data.cobranca_history import (
    remove_supplier_from_df,
    save_charge_to_history,
)
from src.utils.cnpj_validator import validate_cnpj, format_cnpj
import base64
import streamlit.components.v1 as components
from src.ui.preview import _generate_cobranca_html

# ── Constante de limite ───────────────────────────────────────────────────────
CHARGE_THRESHOLD = 400.0

# ── Colunas a exibir ─────────────────────────────────────────────────────────
_DISPLAY_COLS = [
    COLS["date"],
    COLS["supplier"],
    COLS["order"],
    COLS["quantity"],
    COLS["defect"],
    COLS["real_cut"],
    COLS["minutes"],
    COLS["value_brl"],
]

_COL_LABELS = {
    COLS["date"]:      "Data",
    COLS["supplier"]:  "Fornecedor",
    COLS["order"]:     "OM",
    COLS["quantity"]:  "Qtd",
    COLS["defect"]:    "Remonte / Tipo de Defeito",
    COLS["real_cut"]:  "Rel. Cortado",
    COLS["minutes"]:   "Min. Gerados",
    COLS["value_brl"]: "Valor do Processo (R$)",
}


def _render_html_table(df_display: pd.DataFrame, height: int = 400) -> None:
    headers = list(df_display.columns)
    
    TH = (
        "padding:11px 14px;text-align:center;color:#EDE8FF;font-weight:600;"
        "font-size:10px;text-transform:uppercase;letter-spacing:0.9px;"
        "background:#0D0A1E;border-bottom:1px solid rgba(123,94,167,0.35);"
        "white-space:nowrap;position:sticky;top:0;z-index:1;"
    )
    TH_L = TH + "text-align:left;"

    head_html = "".join(
        f'<th style="{TH_L if h in ("Fornecedor", "Remonte / Tipo de Defeito", "Remonte") else TH}">✦ {h}</th>'
        for h in headers
    )

    def _make_cell(h, val, row_bg):
        is_left = h in ("Fornecedor", "Remonte / Tipo de Defeito", "Remonte")
        align = "text-align:left;" if is_left else "text-align:center;"
        base_td = (
            f"padding:9px 14px;font-size:12.5px;color:#F8F6FF;"
            f"border-bottom:1px solid rgba(123,94,167,0.12);"
            f"{align}{row_bg}"
        )
        if h in ("Valor do Processo (R$)", "Valor (R$)"):
            return (
                f'<td style="{base_td}">'
                f'<span style="background:rgba(123,94,167,0.28);color:#F8F6FF;'
                f'padding:3px 9px;border-radius:6px;'
                f'font-size:12px;font-weight:600;white-space:nowrap;">'
                f'{val}</span></td>'
            )
        return f'<td style="{base_td}">{val}</td>'

    rows_html = "".join(
        f"<tr>" + "".join(_make_cell(h, row[h], "background:rgba(123,94,167,0.07);" if i % 2 == 1 else "background:#14112A;") for h in headers) + "</tr>"
        for i, (_, row) in enumerate(df_display.iterrows())
    )

    table_html = f"""
    <style>
      .nv-table-wrap::-webkit-scrollbar {{ width:6px; height:6px; }}
      .nv-table-wrap::-webkit-scrollbar-track {{ background:#0D0A1E; border-radius:3px; }}
      .nv-table-wrap::-webkit-scrollbar-thumb {{ background:rgba(123,94,167,0.45); border-radius:3px; }}
      .nv-table-wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(123,94,167,0.70); }}
      .nv-table-wrap tr:hover td {{ background:rgba(123,94,167,0.14)!important; transition:background 0.15s; }}
    </style>
    <div class="nv-table-wrap" style="
        max-height:{height}px; overflow:auto; border-radius:12px;
        border:1px solid rgba(123,94,167,0.32);
        border-top:2px solid #7B5EA7;
        background:#14112A;
        box-shadow:0 0 22px rgba(123,94,167,0.10);
    ">
      <table style="width:100%;border-collapse:collapse;min-width:980px;">
        <thead><tr>{head_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Pré-visualização — dialog modal
# ══════════════════════════════════════════════════════════════════════════════

@st.dialog("📋 Pré-visualização da Cobrança", width="large")
def _show_preview_dialog(
    supplier: str,
    cnpj: str,
    total: float,
    df_display: pd.DataFrame,
    n_records: int,
    n_orders: int,
) -> None:
    """
    Modal de pré-visualização — cores idênticas à tela Análise de Defeitos.
    Gradiente escuro 1E1019→130C13, acento vermelho #E24B4A, borda roxo #534AB7.
    """
    today_br = date.today().strftime("%d/%m/%Y")

    # ── CSS injetado dentro do dialog ────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* Cabeçalho do dialog */
        [data-testid="stDialogContent"] { background: #0D0D1A !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Banner principal — mesmo estilo dos cards de métricas de defeito ──────
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(160deg, #1E1019 0%, #130C13 100%);
            border: 1px solid rgba(226,75,74,0.32);
            border-top: 3px solid #E24B4A;
            border-radius: 12px;
            padding: 16px 20px 14px;
            margin-bottom: 14px;
            box-shadow: 0 0 28px rgba(226,75,74,0.10), 0 2px 10px rgba(0,0,0,0.40);
        ">
            <div style="display:flex; justify-content:space-between;
                        align-items:flex-start; flex-wrap:wrap; gap:10px;">
                <div>
                    <div style="
                        font-size:10px; color:#EDE8FF;
                        text-transform:uppercase; letter-spacing:0.9px;
                        margin-bottom:5px; font-weight:600;
                    ">
                        <span style="color:#E24B4A; margin-right:5px">✦</span>
                        AVISO DE COBRANÇA — DEFEITOS / REMONTES
                    </div>
                    <div style="font-size:20px; font-weight:700; color:#F8F6FF;
                                line-height:1.2; letter-spacing:-0.3px;">
                        {supplier}
                    </div>
                    <div style="font-size:12px; color:#C8C0F0; margin-top:5px;">
                        CNPJ:&nbsp;
                        <span style="
                            color:#1D9E75; font-weight:700;
                            background:rgba(29,158,117,0.12);
                            padding:1px 8px; border-radius:4px;
                            border:1px solid rgba(29,158,117,0.25);
                        ">{cnpj}</span>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:9px; color:#9898BB; text-transform:uppercase;
                                letter-spacing:0.6px; margin-bottom:3px;">Emissão</div>
                    <div style="font-size:13px; color:#EDE8FF; font-weight:600;">{today_br}</div>
                    <div style="
                        margin-top:6px;
                        font-size:11px; color:#534AB7;
                        background:rgba(83,74,183,0.15);
                        border:1px solid rgba(83,74,183,0.30);
                        padding:2px 10px; border-radius:20px;
                    ">Controle de Qualidade</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI cards — mesmo padrão de _render_summary_metrics ──────────────────
    c1, c2, c3 = st.columns(3)
    _mini_kpi(c1, "✦ TOTAL A COBRAR",  f"R$ {total:,.2f}", "#E24B4A")
    _mini_kpi(c2, "✦ REGISTROS",       str(n_records),      "#534AB7")
    _mini_kpi(c3, "✦ ORDENS (OM)",     str(n_orders),       "#1D9E75")

    # ── Label da tabela ───────────────────────────────────────────────────────
    st.markdown(
        """
        <p style="font-size:10px; color:#EDE8FF; text-transform:uppercase;
                  letter-spacing:0.9px; margin:14px 0 5px; font-weight:600;">
            <span style="color:#E24B4A; margin-right:5px">✦</span>
            DETALHAMENTO DOS REGISTROS
        </p>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabela de registros ───────────────────────────────────────────────────
    _render_html_table(df_display, height=220)

    # ── Barra de total — gradiente vermelho como card de métricas ─────────────
    st.markdown(
        f"""
        <div style="
            display:flex; justify-content:space-between; align-items:center;
            background: linear-gradient(160deg, #1E1019 0%, #130C13 100%);
            border: 1px solid rgba(226,75,74,0.35);
            border-left: 3px solid #E24B4A;
            border-radius: 8px;
            padding: 10px 18px;
            margin-top: 8px;
            box-shadow: 0 0 16px rgba(226,75,74,0.08);
        ">
            <span style="font-size:12px; color:#C8C0F0; line-height:1.5;">
                ⚠️&nbsp; Após confirmar, os registros serão removidos da planilha
                ativa e salvos em&nbsp;
                <code style="
                    color:#7F77DD;
                    background:rgba(83,74,183,0.18);
                    padding:1px 6px; border-radius:3px;
                    font-size:11px;
                ">dataset/bd_cobranca.xlsx</code>
            </span>
            <span style="
                font-size:20px; font-weight:700; color:#E24B4A;
                white-space:nowrap; margin-left:18px;
                text-shadow: 0 0 12px rgba(226,75,74,0.5);
            ">
                R$ {total:,.2f}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Botões de ação ────────────────────────────────────────────────────────
    col_cancel, col_confirm = st.columns([1, 1])
    with col_cancel:
        if st.button("✖ Cancelar", use_container_width=True, key="preview_cancel"):
            st.rerun()
    with col_confirm:
        if st.button(
            "✅ Confirmar e Lançar Cobrança",
            type="primary",
            use_container_width=True,
            key="preview_confirm",
        ):
            st.session_state["_preview_confirmed"] = True
            st.rerun()


def _mini_kpi(col, label: str, value: str, accent: str) -> None:
    """
    Card KPI com gradiente e estilo idêntico a _render_summary_metrics
    (tela Análise de Defeitos).
    """
    with col:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(160deg, #1E1019 0%, #130C13 100%);
                border: 1px solid {accent}52;
                border-top: 2px solid {accent};
                border-radius: 12px;
                padding: 0.9rem 1rem 0.8rem;
                box-shadow: 0 0 20px {accent}1A, 0 2px 8px rgba(0,0,0,0.35);
                text-align: center;
            ">
                <div style="
                    font-size:9px; color:#EDE8FF;
                    text-transform:uppercase; letter-spacing:0.9px;
                    margin-bottom:6px; font-weight:600;
                ">
                    <span style="color:{accent}; margin-right:4px">✦</span>{label}
                </div>
                <div style="
                    font-size:19px; font-weight:700; color:#F8F6FF;
                    line-height:1.2; letter-spacing:-0.3px;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                ">
                    {value}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Entry point público
# ══════════════════════════════════════════════════════════════════════════════

def render_cobranca_page(df: pd.DataFrame) -> None:
    # ── Configurações na Sidebar ──────────────────────────────────────────────
    st.sidebar.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:#6868AA;margin-top:15px;margin-bottom:5px">⚙️ Configurações</p>',
        unsafe_allow_html=True,
    )
    charge_threshold = st.sidebar.number_input(
        "Limite de Cobrança (R$)",
        min_value=0.0,
        value=CHARGE_THRESHOLD,
        step=50.0,
        format="%.2f",
        help="Apenas fornecedores com valor total de desconto acumulado acima deste limite serão listados para cobrança."
    )

    _render_page_header(charge_threshold)

    # ── Calcular totais por fornecedor ────────────────────────────────────────
    supplier_totals = (
        df.groupby(COLS["supplier"])[COLS["value_brl"]]
        .sum()
        .reset_index()
        .rename(columns={COLS["value_brl"]: "_total"})
    )
    above_threshold = supplier_totals[supplier_totals["_total"] > charge_threshold].copy()
    above_threshold = above_threshold.sort_values("_total", ascending=False)

    if above_threshold.empty:
        _render_no_charges(charge_threshold)
        return

    _render_summary_metrics(above_threshold)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="border-top:1px solid {COLORS["border"]};margin-bottom:18px"></div>',
        unsafe_allow_html=True,
    )

    # ── Seletor de fornecedor ─────────────────────────────────────────────────
    supplier_options = above_threshold[COLS["supplier"]].tolist()
    total_map = dict(zip(above_threshold[COLS["supplier"]], above_threshold["_total"]))

    selected_supplier = st.selectbox(
        "🏭 Selecionar Fornecedor para Cobrança",
        options=supplier_options,
        format_func=lambda s: f"{s}  —  R$ {total_map.get(s, 0):,.2f}",
        key="cobranca_supplier_select",
    )

    sel_row   = above_threshold[above_threshold[COLS["supplier"]] == selected_supplier].iloc[0]
    sel_total = sel_row["_total"]

    _render_supplier_badge(selected_supplier, sel_total)

    # ── Input CNPJ ────────────────────────────────────────────────────────────
    cnpj_valid, cnpj_formatted = _render_cnpj_input(selected_supplier)

    # ── Tabela de registros ───────────────────────────────────────────────────
    st.markdown(
        f'<p style="font-size:12px;color:{COLORS["text_subtle"]}; '
        f'text-transform:uppercase;letter-spacing:0.6px;margin:18px 0 6px">'
        f'📋 Registros de Defeito — {selected_supplier}</p>',
        unsafe_allow_html=True,
    )

    df_sel = df[df[COLS["supplier"]] == selected_supplier][_DISPLAY_COLS].copy()
    df_sel[COLS["date"]] = df_sel[COLS["date"]].dt.strftime("%d/%m/%Y")

    display_rename = {c: _COL_LABELS[c] for c in _DISPLAY_COLS if c in df_sel.columns}
    df_display = df_sel.rename(columns=display_rename)

    val_label = _COL_LABELS[COLS["value_brl"]]
    df_display[val_label] = df_display[val_label].apply(
        lambda v: f"R$ {float(v):,.2f}" if v != "" else ""
    )

    df_display["Qtd"] = df_display["Qtd"].apply(lambda v: f"{int(v):,}" if pd.notna(v) and v != "" else "")
    df_display["Rel. Cortado"] = df_display["Rel. Cortado"].apply(lambda v: f"{int(v):,}" if pd.notna(v) and v != "" else "")
    df_display["Min. Gerados"] = df_display["Min. Gerados"].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) and v != "" else "")

    _render_html_table(df_display, height=min(460, max(160, (len(df_display) + 1) * 38)))

    # Total visual
    st.markdown(
        f"""
        <div style="
            display:flex; justify-content:flex-end; align-items:center;
            background:rgba(194,57,43,0.12);
            border:1px solid rgba(194,57,43,0.35);
            border-radius:8px; padding:10px 18px; margin-top:8px;
        ">
            <span style="font-size:13px;color:{COLORS['text_muted']};margin-right:12px">
                Total a Cobrar:
            </span>
            <span style="font-size:18px;font-weight:700;color:#E74C3C">
                R$ {sel_total:,.2f}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ── Botões de ação (preview + lançar) ────────────────────────────────────
    _render_charge_button(
        supplier=selected_supplier,
        cnpj=cnpj_formatted,
        total=sel_total,
        df_records=df_sel,
        df_display=df_display,
        cnpj_valid=cnpj_valid,
        df_full=df,
    )



# ══════════════════════════════════════════════════════════════════════════════
# Render helpers privados
# ══════════════════════════════════════════════════════════════════════════════

def _render_page_header(charge_threshold: float) -> None:
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;
                    border-bottom:1px solid rgba(255,255,255,0.06);
                    margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;
                             color:{COLORS['text_primary']}">
                    💰 Cobrança de Fornecedores
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(83,74,183,0.18);
                             padding:3px 10px;border-radius:20px;
                             border:1px solid rgba(83,74,183,0.3)">
                    Gestão de Desconto
                </span>
            </div>
            <p style="color:{COLORS['text_muted']};font-size:13px;margin:5px 0 0">
                Fornecedores com valor total de desconto acima de
                <strong style="color:{COLORS['text_primary']}">R$ {charge_threshold:,.2f}</strong>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_no_charges(charge_threshold: float) -> None:
    st.markdown(
        f"""
        <div style="
            display:flex; flex-direction:column; align-items:center;
            justify-content:center; min-height:40vh; text-align:center; gap:14px;
        ">
            <div style="font-size:48px; opacity:0.25">✅</div>
            <p style="font-size:20px; font-weight:600;
                      color:{COLORS['text_primary']}; margin:0">
                Nenhuma cobrança a realizar
            </p>
            <p style="font-size:13px; color:{COLORS['text_subtle']};
                      margin:0; max-width:380px; line-height:1.6">
                Nenhum fornecedor atingiu o limite de
                <strong>R$ {charge_threshold:,.2f}</strong>
                de desconto acumulado no período carregado.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_metrics(above_threshold: pd.DataFrame) -> None:
    n_suppliers  = len(above_threshold)
    total_value  = above_threshold["_total"].sum()
    max_supplier = above_threshold.iloc[0][COLS["supplier"]]
    max_value    = above_threshold.iloc[0]["_total"]

    _NV  = "#E24B4A"
    _BG1 = "#1E1019"
    _BG2 = "#130C13"

    card_style = f"""
        background:linear-gradient(160deg,{_BG1} 0%,{_BG2} 100%);
        border:1px solid rgba(226,75,74,0.32);
        border-top:2px solid {_NV};
        border-radius:12px;
        padding:1.1rem 1.2rem 1rem;
        box-shadow:0 0 22px rgba(226,75,74,0.10), 0 2px 8px rgba(0,0,0,0.35);
    """

    c1, c2, c3 = st.columns(3)
    cards = [
        (c1, "⚠️ FORNECEDORES A COBRAR", str(n_suppliers),        "com valor acima do limite"),
        (c2, "💰 VALOR TOTAL PENDENTE",  f"R$ {total_value:,.2f}", "soma de todos os fornecedores"),
        (c3, "🔴 MAIOR DEVEDOR",         max_supplier,             f"R$ {max_value:,.2f}"),
    ]
    for col, label, value, sub in cards:
        with col:
            st.markdown(
                f"""
                <div style="{card_style}">
                    <div style="font-size:10px;color:#EDE8FF;
                                text-transform:uppercase;letter-spacing:0.9px;
                                margin-bottom:8px;font-weight:600">
                        <span style="color:{_NV};margin-right:5px">✦</span>{label}
                    </div>
                    <div style="font-size:20px;font-weight:700;color:#F8F6FF;
                                line-height:1.2;letter-spacing:-0.3px;
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        {value}
                    </div>
                    <div style="font-size:11px;color:#C8C0F0;margin-top:5px">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_supplier_badge(supplier: str, total: float) -> None:
    st.markdown(
        f"""
        <div style="
            background:rgba(83,74,183,0.10);
            border:1px solid rgba(83,74,183,0.28);
            border-radius:10px;
            padding:10px 16px;
            display:flex; gap:24px; flex-wrap:wrap;
            margin-bottom:6px; margin-top:4px;
        ">
            <div>
                <span style="font-size:10px;color:{COLORS['text_subtle']};
                             text-transform:uppercase;letter-spacing:0.5px">
                    Fornecedor
                </span><br>
                <span style="font-size:13px;font-weight:600;
                             color:{COLORS['text_primary']}">{supplier}</span>
            </div>
            <div>
                <span style="font-size:10px;color:{COLORS['text_subtle']};
                             text-transform:uppercase;letter-spacing:0.5px">
                    Total a Cobrar
                </span><br>
                <span style="font-size:14px;font-weight:700;color:#E74C3C">
                    R$ {total:,.2f}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_cnpj_input(supplier: str) -> tuple[bool, str]:
    st.markdown(
        f"""
        <div style="
            margin:16px 0 10px;
            padding:12px 16px 4px;
            background:rgba(83,74,183,0.06);
            border:1px solid rgba(83,74,183,0.20);
            border-left:3px solid {COLORS['primary']};
            border-radius:8px;
        ">
            <p style="font-size:11px;color:{COLORS['text_subtle']};
                      text-transform:uppercase;letter-spacing:0.7px;margin:0 0 8px">
                🔐 CNPJ do Fornecedor — obrigatório para lançamento
            </p>
        """,
        unsafe_allow_html=True,
    )

    col_input, col_feedback = st.columns([1, 2])

    with col_input:
        cnpj_raw = st.text_input(
            "CNPJ",
            placeholder="XX.XXX.XXX/XXXX-XX",
            max_chars=18,
            key=f"cnpj_input_{supplier}",
            label_visibility="collapsed",
            help="Digite o CNPJ com ou sem formatação.",
        )

    cnpj_valid     = False
    cnpj_formatted = ""

    with col_feedback:
        if not cnpj_raw or cnpj_raw.strip() == "":
            st.markdown(
                """
                <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;
                    background:rgba(239,159,39,0.08);border:1px solid rgba(239,159,39,0.28);
                    border-radius:7px;margin-top:2px;">
                    <span style="font-size:15px">⚠️</span>
                    <span style="font-size:12px;color:#EF9F27;font-weight:500">
                        CNPJ não informado — lançamento bloqueado.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif validate_cnpj(cnpj_raw):
            cnpj_valid     = True
            cnpj_formatted = format_cnpj(cnpj_raw)
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;
                    background:rgba(29,158,117,0.10);border:1px solid rgba(29,158,117,0.30);
                    border-radius:7px;margin-top:2px;">
                    <span style="font-size:15px">✅</span>
                    <span style="font-size:12px;color:#1D9E75;font-weight:600">
                        CNPJ válido: {cnpj_formatted}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                """
                <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;
                    background:rgba(226,75,74,0.10);border:1px solid rgba(226,75,74,0.30);
                    border-radius:7px;margin-top:2px;">
                    <span style="font-size:15px">❌</span>
                    <span style="font-size:12px;color:#E24B4A;font-weight:500">
                        CNPJ inválido — verifique o número informado.
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)
    return cnpj_valid, cnpj_formatted


def _render_charge_button(
    supplier: str,
    cnpj: str,
    total: float,
    df_records: pd.DataFrame,
    df_display: pd.DataFrame,
    cnpj_valid: bool,
    df_full: pd.DataFrame,
) -> None:
    """
    Gerencia o fluxo:
      1. Botão "Pré-visualizar" → abre modal com detalhes
      2. Dentro do modal: "Confirmar e Lançar"
         → gera Excel, salva bd_cobranca, remove fornecedor do df
      3. Estado: "Cobrança lançada" com download disponível
    """
    charge_key     = f"charge_confirmed_{supplier}"
    charge_doc_key = f"charge_doc_{supplier}"

    # ── Processar confirmação vinda do modal ──────────────────────────────────
    if st.session_state.pop("_preview_confirmed", False):
        with st.spinner("Salvando cobrança e atualizando base de dados…"):
            # 1. Prepara df para exportação
            df_export = df_records[[c for c in _DISPLAY_COLS if c in df_records.columns]].copy()
            date_col  = COLS["date"]
            if df_export[date_col].dtype == object:
                df_export[date_col] = pd.to_datetime(
                    df_export[date_col], dayfirst=True, errors="coerce"
                )

            # 2. Gera documento Excel da cobrança
            excel_bytes = generate_charge_excel(
                supplier=supplier,
                cnpj=cnpj,
                df_records=df_export,
                display_cols=_DISPLAY_COLS,
                col_labels=_COL_LABELS,
            )

            # Gera HTML da cobrança
            html_page = _generate_cobranca_html(
                supplier=supplier,
                cnpj=cnpj,
                total=total,
                df_sel=df_records,
                df_full=df_full,
            )

            # 3. Salva no histórico bd_cobranca.xlsx
            save_charge_to_history(
                supplier=supplier,
                cnpj=cnpj,
                total=total,
                df_records=df_export,
                display_cols=_DISPLAY_COLS,
            )

            # 4. Remove fornecedor do DataFrame ativo
            remove_supplier_from_df(supplier, COLS["supplier"])

        now_str = date.today().strftime("%d/%m/%Y")
        st.session_state[charge_key]                = True
        st.session_state[charge_doc_key]            = excel_bytes
        st.session_state[f"charge_html_{supplier}"] = html_page
        st.session_state[f"charge_time_{supplier}"] = now_str
        st.rerun()

    already_launched = st.session_state.get(charge_key, False)

    if already_launched:
        # ── Estado: cobrança lançada ──────────────────────────────────────────
        launched_at = st.session_state.get(f"charge_time_{supplier}", "")
        st.markdown(
            f"""
            <div style="
                background:rgba(29,158,117,0.12);
                border:1px solid rgba(29,158,117,0.35);
                border-radius:10px; padding:14px 18px;
            ">
                <span style="font-size:14px;font-weight:600;color:#1D9E75">
                    ✅ Cobrança lançada com sucesso
                </span>
                <p style="font-size:12px;color:{COLORS['text_muted']};margin:4px 0 0">
                    Fornecedor: <strong>{supplier}</strong> —
                    Emitida em: {launched_at} —
                    Registros removidos da planilha ativa e salvos em
                    <code style="color:#534AB7">dataset/bd_cobranca.xlsx</code>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        col_excel, col_pdf_preview = st.columns(2)
        with col_excel:
            if charge_doc_key in st.session_state:
                st.download_button(
                    label="⬇️ Baixar Documento de Cobrança (Excel)",
                    data=st.session_state[charge_doc_key],
                    file_name=f"cobranca_{supplier.replace(' ', '_')}_{date.today().isoformat()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_after_{supplier}",
                    use_container_width=True,
                )
        with col_pdf_preview:
            html_page = st.session_state.get(f"charge_html_{supplier}", "")
            if html_page:
                html_b64 = base64.b64encode(html_page.encode("utf-8")).decode()
                components.html(
                    f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  .btn {{
    display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; height: 38px; border-radius: 8px; cursor: pointer;
    font-size: 12.5px; font-weight: 500;
    transition: all .15s ease;
    background: rgba(83,74,183,0.15);
    color: #B8B0FF;
    border: 1px solid rgba(83,74,183,0.35);
  }}
  .btn:hover {{
    background: rgba(83,74,183,0.28);
    border-color: rgba(83,74,183,0.6);
  }}
  .btn:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
<button class="btn" onclick="openPreview()">📄 Prévia / Imprimir PDF</button>
<script>
  const _HTML_B64 = "{html_b64}";
  function openPreview() {{
    try {{
      const bytes = Uint8Array.from(atob(_HTML_B64), c => c.charCodeAt(0));
      const html  = new TextDecoder("utf-8").decode(bytes);
      const win   = window.open("", "_blank");
      if (win) {{
        win.document.open();
        win.document.write(html);
        win.document.close();
      }} else {{
        const blob = new Blob([html], {{ type: "text/html;charset=utf-8" }});
        window.open(URL.createObjectURL(blob), "_blank");
      }}
    }} catch (err) {{
      console.error(err);
      alert("Erro ao abrir prévia. Permita popups.");
    }}
  }}
</script>
</body>
</html>""",
                    height=38,
                    scrolling=False,
                )

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        if st.button("↺ Relançar / Emitir Novo Documento", key=f"relaunch_{supplier}", use_container_width=True):
            st.session_state.pop(charge_key, None)
            st.session_state.pop(charge_doc_key, None)
            st.session_state.pop(f"charge_html_{supplier}", None)
            st.session_state.pop(f"charge_time_{supplier}", None)
            st.rerun()
        return

    # ── CNPJ ausente ou inválido ──────────────────────────────────────────────
    if not cnpj_valid:
        st.markdown(
            f"""
            <div style="
                display:flex; align-items:center; gap:12px;
                background:rgba(239,159,39,0.07);
                border:1px solid rgba(239,159,39,0.22);
                border-radius:10px; padding:14px 18px;
            ">
                <span style="font-size:22px">🔒</span>
                <div>
                    <p style="font-size:13px;color:#EF9F27;font-weight:600;margin:0">
                        Lançamento bloqueado
                    </p>
                    <p style="font-size:12px;color:{COLORS['text_muted']};margin:3px 0 0">
                        Informe e valide o CNPJ acima para liberar os botões de ação.
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── CNPJ válido: botões Preview + Lançar ─────────────────────────────────
    n_records = len(df_records)
    n_orders  = df_records[COLS["order"]].nunique() if COLS["order"] in df_records.columns else 0

    col_preview, col_launch, col_pdf, col_info = st.columns([1, 1, 1, 1.5])

    with col_preview:
        if st.button(
            "🔍 Pré-visualizar Cobrança",
            use_container_width=True,
            key=f"preview_{supplier}",
        ):
            _show_preview_dialog(
                supplier=supplier,
                cnpj=cnpj,
                total=total,
                df_display=df_display,
                n_records=n_records,
                n_orders=n_orders,
            )

    with col_launch:
        if st.button(
            f"🚀 Lançar — R$ {total:,.2f}",
            type="primary",
            use_container_width=True,
            key=f"launch_{supplier}",
        ):
            st.session_state["_preview_confirmed"] = True
            st.rerun()

    with col_pdf:
        # Gera HTML da cobrança
        html_page = _generate_cobranca_html(
            supplier=supplier,
            cnpj=cnpj,
            total=total,
            df_sel=df_records,
            df_full=df_full,
        )
        html_b64 = base64.b64encode(html_page.encode("utf-8")).decode()
        components.html(
            f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }}
  .btn {{
    display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; height: 38px; border-radius: 8px; cursor: pointer;
    font-size: 12px; font-weight: 500;
    transition: all .15s ease;
    background: rgba(83,74,183,0.15);
    color: #B8B0FF;
    border: 1px solid rgba(83,74,183,0.35);
  }}
  .btn:hover {{
    background: rgba(83,74,183,0.28);
    border-color: rgba(83,74,183,0.6);
  }}
  .btn:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
<button class="btn" onclick="openPreview()">📄 Prévia / Imprimir PDF</button>
<script>
  const _HTML_B64 = "{html_b64}";
  function openPreview() {{
    try {{
      const bytes = Uint8Array.from(atob(_HTML_B64), c => c.charCodeAt(0));
      const html  = new TextDecoder("utf-8").decode(bytes);
      const win   = window.open("", "_blank");
      if (win) {{
        win.document.open();
        win.document.write(html);
        win.document.close();
      }} else {{
        const blob = new Blob([html], {{ type: "text/html;charset=utf-8" }});
        window.open(URL.createObjectURL(blob), "_blank");
      }}
    }} catch (err) {{
      console.error(err);
      alert("Erro ao abrir prévia. Permita popups.");
    }}
  }}
</script>
</body>
</html>""",
            height=38,
            scrolling=False,
        )

    with col_info:
        st.markdown(
            f"""
            <div style="padding:8px 0;font-size:11px;color:{COLORS['text_muted']}">
                Fornecedor: <strong style="color:{COLORS['text_primary']}">{supplier}</strong> ·
                CNPJ: <strong style="color:{COLORS['teal']}">{cnpj}</strong> ·
                <strong style="color:#E74C3C">R$ {total:,.2f}</strong>
                <span style="display:block;font-size:9.5px;color:#4A4A80;margin-top:2px">
                    Use Pré-visualizar ou Prévia / Imprimir para revisar.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )


# (histórico movido para pages/3_Historico_Cobranca.py — v12)
