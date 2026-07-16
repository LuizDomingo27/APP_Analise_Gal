# -*- coding: utf-8 -*-
"""
UI da página de Cobrança de Fornecedores.

CHANGELOG v13:
- Refatoração arquitetural: importações atualizadas para novas camadas.
- Validação de CNPJ movida para src/utils/cnpj_validator.py.
- Exportadores movidos para src/services/.
- Histórico movido para src/data/cobranca_history.py.
"""

import logging
import math
from datetime import date, timedelta

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

from src.config.settings import COLS, COLORS
from src.services.charge_exporter import generate_charge_excel
from src.data.database import DatabaseUnavailableError
from src.data.cobranca_history import (
    ChargeAlreadyLaunchedError,
    launch_charge,
)
from src.data.divida_dividida import split_records
from src.utils.cnpj_validator import validate_cnpj, format_cnpj
from src.auth.session import is_admin
import base64
import streamlit.components.v1 as components
from src.ui.preview import _generate_cobranca_html

# ── Constante de limite ───────────────────────────────────────────────────────
CHARGE_THRESHOLD = 400.0


# ── Formatação segura de células numéricas ────────────────────────────────────
# As colunas de origem (ex.: "REAL CORTADO") têm dtype object e podem conter
# strings não convertíveis diretamente (separador decimal/milhar, "nan", texto).
# Estas funções nunca lançam: valores ausentes viram "" e valores não numéricos
# são exibidos como estão, evitando derrubar a página inteira.
def _coerce_number(v):
    """Converte v para float finito ou retorna None se não for possível.

    Cobre NaN/None, strings vazias, strings numéricas ("1240") e valores
    não numéricos ou não finitos ("nan", "abc", inf) — nestes casos, None.
    """
    if pd.isna(v) or v == "":
        return None
    try:
        n = float(v)
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) else None


def _fmt_int_cell(v):
    n = _coerce_number(v)
    if n is None:
        return "" if (pd.isna(v) or v == "") else str(v)
    return f"{int(n):,}"


def _fmt_float_cell(v):
    n = _coerce_number(v)
    if n is None:
        return "" if (pd.isna(v) or v == "") else str(v)
    return f"{n:,.2f}"

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
        "padding:11px 14px;text-align:center;color:#FFFFFF;font-weight:600;"
        "font-size:11px;text-transform:uppercase;letter-spacing:0.7px;"
        "background:#00805C;border-bottom:2px solid #00B884;"
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
            f"padding:9px 14px;font-size:12.5px;color:#0D1B17;"
            f"border-bottom:1px solid rgba(0,229,160,0.12);"
            f"{align}{row_bg}"
        )
        if h in ("Valor do Processo (R$)", "Valor (R$)"):
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
    data_cobranca: date,
    data_vencimento: date,
    dias_para_vencer: int,
) -> None:
    """
    Modal de pré-visualização — cores idênticas à tela Análise de Defeitos.
    Gradiente escuro 1E1019→130C13, acento vermelho #E24B4A, borda roxo #00B884.
    """
    today_br = date.today().strftime("%d/%m/%Y")
    dias_texto, dias_accent = _dias_para_vencer_label(dias_para_vencer)

    # ── CSS injetado dentro do dialog ────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* Cabeçalho do dialog */
        [data-testid="stDialogContent"] { background: #FAFCFB !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Banner principal — mesmo estilo dos cards de métricas de defeito ──────
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(160deg, #FFFFFF 0%, #F2F7F5 100%);
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
                        font-size:10px; color:#0D1B17;
                        text-transform:uppercase; letter-spacing:0.9px;
                        margin-bottom:5px; font-weight:600;
                    ">
                        <span style="color:#E24B4A; margin-right:5px">✦</span>
                        AVISO DE COBRANÇA — DEFEITOS / REMONTES
                    </div>
                    <div style="font-size:20px; font-weight:700; color:#0D1B17;
                                line-height:1.2; letter-spacing:-0.3px;">
                        {supplier}
                    </div>
                    <div style="font-size:12px; color:#4A5752; margin-top:5px;">
                        CNPJ:&nbsp;
                        <span style="
                            color:#00805C; font-weight:700;
                            background:rgba(0,229,160,0.12);
                            padding:1px 8px; border-radius:4px;
                            border:1px solid rgba(0,229,160,0.25);
                        ">{cnpj}</span>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:9px; color:#4A5752; text-transform:uppercase;
                                letter-spacing:0.6px; margin-bottom:3px;">Emissão</div>
                    <div style="font-size:13px; color:#0D1B17; font-weight:600;">{today_br}</div>
                    <div style="
                        margin-top:6px;
                        font-size:11px; color:#0D1B17;
                        background:rgba(0,229,160,0.15);
                        border:1px solid rgba(0,229,160,0.30);
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
    _mini_kpi(c2, "✦ REGISTROS",       str(n_records),      "#00B884")
    _mini_kpi(c3, "✦ ORDENS (OM)",     str(n_orders),       "#00E5A0")

    # ── KPI cards — prazo da cobrança (data/vencimento/dias a vencer) ────────
    c4, c5, c6 = st.columns(3)
    _mini_kpi(c4, "✦ DATA DA COBRANÇA",   data_cobranca.strftime("%d/%m/%Y"),   "#0EA5C7")
    _mini_kpi(c5, "✦ VENCIMENTO (+20D)",  data_vencimento.strftime("%d/%m/%Y"), "#7C8985")
    _mini_kpi(c6, "✦ DIAS PARA VENCER",   dias_texto,                           dias_accent)

    # ── Label da tabela ───────────────────────────────────────────────────────
    st.markdown(
        """
        <p style="font-size:10px; color:#0D1B17; text-transform:uppercase;
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
            background: linear-gradient(160deg, #FFFFFF 0%, #F2F7F5 100%);
            border: 1px solid rgba(226,75,74,0.35);
            border-left: 3px solid #E24B4A;
            border-radius: 8px;
            padding: 10px 18px;
            margin-top: 8px;
            box-shadow: 0 0 16px rgba(226,75,74,0.08);
        ">
            <span style="font-size:12px; color:#4A5752; line-height:1.5;">
                ⚠️&nbsp; Após confirmar, os registros serão removidos da planilha
                ativa e salvos em&nbsp;
                <code style="
                    color:#00805C;
                    background:rgba(0,229,160,0.18);
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
            disabled=not is_admin(),
            help=None if is_admin() else "Apenas administradores podem lançar cobranças.",
        ):
            st.session_state["_preview_confirmed"] = True
            st.rerun()


def _dias_para_vencer_label(dias_para_vencer: int) -> tuple[str, str]:
    """
    Retorna (texto, cor) para o indicador de Dias para Vencer:
      - negativo -> vencido (vermelho)
      - zero     -> vence hoje (âmbar)
      - positivo -> dias restantes (verde)
    """
    if dias_para_vencer < 0:
        return f"Vencido há {abs(dias_para_vencer)} dia(s)", "#E24B4A"
    if dias_para_vencer == 0:
        return "Vence hoje", "#EF9F27"
    return f"{dias_para_vencer} dia(s)", "#00805C"


def _render_charge_dates_input(supplier: str) -> tuple[date, date, int]:
    """
    Campos de prazo da cobrança, exibidos na tela principal de Cobrança
    de Fornecedores (refletidos depois na pré-visualização e no PDF):

      - Data da Cobrança:   escolhida livremente pelo usuário.
      - Data de Vencimento: calculada automaticamente = Data da Cobrança + 20 dias.
      - Dias para Vencer:   contagem regressiva entre hoje e a Data de Vencimento.
    """
    st.markdown(
        f"""
        <p style="font-size:11px;color:{COLORS['text_subtle']};
                  text-transform:uppercase;letter-spacing:0.7px;margin:16px 0 8px">
            📅 Prazo da Cobrança
        </p>
        """,
        unsafe_allow_html=True,
    )

    col_cobranca, col_vencimento, col_dias = st.columns(3)

    with col_cobranca:
        data_cobranca = st.date_input(
            "Data da Cobrança",
            value=date.today(),
            format="DD/MM/YYYY",
            key=f"data_cobranca_{supplier}",
            help="Data em que a cobrança está sendo realizada junto ao fornecedor. "
                 "O vencimento é calculado automaticamente (+20 dias).",
        )

    data_vencimento  = data_cobranca + timedelta(days=20)
    dias_para_vencer = (data_vencimento - date.today()).days
    dias_texto, dias_accent = _dias_para_vencer_label(dias_para_vencer)

    with col_vencimento:
        st.markdown(
            f"""
            <div style="margin-top:1.8rem">
              <span style="font-size:11px;color:{COLORS['text_subtle']};
                          text-transform:uppercase;letter-spacing:0.5px">
                  🔒 Data de Vencimento
              </span><br>
              <span style="font-size:15px;font-weight:700;color:{COLORS['text_primary']}">
                  {data_vencimento.strftime('%d/%m/%Y')}
              </span>
              <span style="display:block;font-size:10px;color:{COLORS['text_subtle']};margin-top:1px">
                  Cobrança + 20 dias (automático)
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_dias:
        st.markdown(
            f"""
            <div style="margin-top:1.8rem">
              <span style="font-size:11px;color:{COLORS['text_subtle']};
                          text-transform:uppercase;letter-spacing:0.5px">
                  ⏳ Dias para Vencer
              </span><br>
              <span style="font-size:15px;font-weight:700;color:{dias_accent}">
                  {dias_texto}
              </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return data_cobranca, data_vencimento, dias_para_vencer


def _mini_kpi(col, label: str, value: str, accent: str) -> None:
    """
    Card KPI com gradiente e estilo idêntico a _render_summary_metrics
    (tela Análise de Defeitos).
    """
    with col:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(160deg, #FFFFFF 0%, #F2F7F5 100%);
                border: 1px solid {accent}52;
                border-top: 2px solid {accent};
                border-radius: 12px;
                padding: 0.9rem 1rem 0.8rem;
                box-shadow: 0 0 20px {accent}1A, 0 2px 8px rgba(0,0,0,0.35);
                text-align: center;
            ">
                <div style="
                    font-size:9px; color:#0D1B17;
                    text-transform:uppercase; letter-spacing:0.9px;
                    margin-bottom:6px; font-weight:600;
                ">
                    <span style="color:{accent}; margin-right:4px">✦</span>{label}
                </div>
                <div style="
                    font-size:19px; font-weight:700; color:#0D1B17;
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
    # ── Configurações — inline (esta aba não tem uma sidebar dedicada,
    # pois convive com as abas de Histórico e Pagamentos na mesma página) ──────
    col_cfg, col_info = st.columns([1, 2])
    with col_cfg:
        charge_threshold = st.number_input(
            "Limite de Cobrança (R$)",
            min_value=0.0,
            value=CHARGE_THRESHOLD,
            step=50.0,
            format="%.2f",
            help="Apenas fornecedores com valor total de desconto acumulado acima deste limite serão listados para cobrança.",
            key="cobranca_charge_threshold",
        )
    with col_info:
        st.markdown(
            f"""
            <div style="margin-top:1.8rem;font-size:11px;color:{COLORS.get('text_subtle', '#7C8985')}">
                🗃️ {len(df):,} registros na base
            </div>
            """,
            unsafe_allow_html=True,
        )

    _render_page_header(charge_threshold)

    # ── Filtro de Período de Referência ───────────────────────────────────────
    date_start, date_end = _render_reference_date_filter(df)
    df = df[
        (df[COLS["date"]].dt.date >= date_start)
        & (df[COLS["date"]].dt.date <= date_end)
    ].copy()

    if df.empty:
        _render_no_records_for_date(date_start, date_end)
        return

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

    # ── Prazo da cobrança (data cobrança / vencimento / dias a vencer) ───────
    data_cobranca, data_vencimento, dias_para_vencer = _render_charge_dates_input(selected_supplier)

    # ── Divisão da cobrança (opcional) ────────────────────────────────────────
    split_active, perc_frac = _render_split_input(selected_supplier, sel_total)

    # ── Tabela de registros ───────────────────────────────────────────────────
    st.markdown(
        f'<p style="font-size:12px;color:{COLORS["text_subtle"]}; '
        f'text-transform:uppercase;letter-spacing:0.6px;margin:18px 0 6px">'
        f'📋 Registros de Defeito — {selected_supplier}</p>',
        unsafe_allow_html=True,
    )

    df_sel = df[df[COLS["supplier"]] == selected_supplier][_DISPLAY_COLS].copy()
    df_sel[COLS["date"]] = df_sel[COLS["date"]].dt.strftime("%d/%m/%Y")

    # Quando a cobrança é dividida, tudo que é exibido/pré-visualizado/impresso e
    # gravado para o fornecedor passa a ser a metade corrigida. A metade da
    # empresa (df_empresa) é preservada para gravar em tb_divida_dividida.
    if split_active:
        df_fornecedor, df_empresa = split_records(df_sel, perc_frac)
    else:
        df_fornecedor, df_empresa = df_sel, None
    charge_total = float(
        pd.to_numeric(df_fornecedor[COLS["value_brl"]], errors="coerce").fillna(0).sum()
    )

    display_rename = {c: _COL_LABELS[c] for c in _DISPLAY_COLS if c in df_fornecedor.columns}
    df_display = df_fornecedor.rename(columns=display_rename)

    val_label = _COL_LABELS[COLS["value_brl"]]
    df_display[val_label] = df_display[val_label].apply(
        lambda v: f"R$ {_coerce_number(v):,.2f}" if _coerce_number(v) is not None else ""
    )

    df_display["Qtd"] = df_display["Qtd"].apply(_fmt_int_cell)
    df_display["Rel. Cortado"] = df_display["Rel. Cortado"].apply(_fmt_int_cell)
    df_display["Min. Gerados"] = df_display["Min. Gerados"].apply(_fmt_float_cell)

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
                Total a Cobrar{' (dividido)' if split_active else ''}:
            </span>
            <span style="font-size:18px;font-weight:700;color:#E74C3C">
                R$ {charge_total:,.2f}
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
        total=charge_total,
        df_records=df_fornecedor,
        df_display=df_display,
        cnpj_valid=cnpj_valid,
        df_full=df,
        data_cobranca=data_cobranca,
        data_vencimento=data_vencimento,
        dias_para_vencer=dias_para_vencer,
        reference_date=date_start,
        reference_date_end=date_end,
        split_active=split_active,
        df_records_empresa=df_empresa,
    )



# ══════════════════════════════════════════════════════════════════════════════
# Render helpers privados
# ══════════════════════════════════════════════════════════════════════════════

def _render_page_header(charge_threshold: float) -> None:
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;
                    border-bottom:1px solid rgba(0,0,0,0.06);
                    margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;
                             color:{COLORS['text_primary']}">
                    💰 Cobrança de Fornecedores
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(0,229,160,0.18);
                             padding:3px 10px;border-radius:20px;
                             border:1px solid rgba(0,229,160,0.3)">
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


def _render_reference_date_filter(df: pd.DataFrame) -> tuple[date, date]:
    """
    Filtro de Período de Referência: define o intervalo de datas de produção
    cujos registros serão considerados para o cálculo e lançamento da
    cobrança. Apenas fornecedores com registros nesse intervalo são
    exibidos, e o lançamento remove/move apenas os registros do intervalo.

    Apresentado como dois campos explícitos — Data Inicial e Data Final —
    para deixar claro que se trata de um filtro "de uma data até outra data".
    """
    available_dates = sorted(df[COLS["date"]].dt.date.unique())
    min_date = available_dates[0]  if available_dates else date.today()
    max_date = available_dates[-1] if available_dates else date.today()

    st.markdown(
        f"""
        <p style="font-size:11px;color:{COLORS['text_subtle']};
                  text-transform:uppercase;letter-spacing:0.7px;margin:0 0 8px">
            📅 Período de Referência da Cobrança — filtre de uma data até outra
        </p>
        """,
        unsafe_allow_html=True,
    )

    col_start, col_end, col_hint = st.columns([1, 1, 2])

    with col_start:
        date_start = st.date_input(
            "De (Data Inicial)",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
            key="cobranca_reference_date_start",
            help="Data inicial do período. Somente registros produzidos a "
                 "partir desta data (inclusive) serão considerados.",
        )

    with col_end:
        date_end = st.date_input(
            "Até (Data Final)",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
            key="cobranca_reference_date_end",
            help="Data final do período. Somente registros produzidos até "
                 "esta data (inclusive) serão considerados.",
        )

    # Se o usuário inverter as datas, normaliza para não quebrar o filtro.
    if date_start > date_end:
        date_start, date_end = date_end, date_start

    with col_hint:
        period_label = (
            date_start.strftime('%d/%m/%Y')
            if date_start == date_end
            else f"{date_start.strftime('%d/%m/%Y')} até {date_end.strftime('%d/%m/%Y')}"
        )
        st.markdown(
            f"""
            <div style="margin-top:1.8rem;font-size:12px;color:{COLORS['text_subtle']}">
                Apenas registros produzidos entre <strong>{period_label}</strong>
                serão considerados. Ao lançar, somente os registros desse período
                são removidos da planilha ativa e movidos para o histórico.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="border-top:1px solid {COLORS["border"]};margin-bottom:18px"></div>',
        unsafe_allow_html=True,
    )

    return date_start, date_end


def _render_no_records_for_date(date_start: date, date_end: date) -> None:
    period_label = (
        date_start.strftime('%d/%m/%Y')
        if date_start == date_end
        else f"{date_start.strftime('%d/%m/%Y')} até {date_end.strftime('%d/%m/%Y')}"
    )
    st.markdown(
        f"""
        <div style="
            display:flex; flex-direction:column; align-items:center;
            justify-content:center; min-height:30vh; text-align:center; gap:14px;
        ">
            <div style="font-size:48px; opacity:0.25">📭</div>
            <p style="font-size:18px; font-weight:600;
                      color:{COLORS['text_primary']}; margin:0">
                Nenhum registro para {period_label}
            </p>
            <p style="font-size:13px; color:{COLORS['text_subtle']};
                      margin:0; max-width:380px; line-height:1.6">
                Selecione outro Período de Referência acima para visualizar as
                cobranças correspondentes.
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
    _BG1 = "#FFFFFF"
    _BG2 = "#F2F7F5"

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
                    <div style="font-size:10px;color:#0D1B17;
                                text-transform:uppercase;letter-spacing:0.9px;
                                margin-bottom:8px;font-weight:600">
                        <span style="color:{_NV};margin-right:5px">✦</span>{label}
                    </div>
                    <div style="font-size:20px;font-weight:700;color:#0D1B17;
                                line-height:1.2;letter-spacing:-0.3px;
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        {value}
                    </div>
                    <div style="font-size:11px;color:#4A5752;margin-top:5px">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_supplier_badge(supplier: str, total: float) -> None:
    st.markdown(
        f"""
        <div style="
            background:rgba(0,229,160,0.10);
            border:1px solid rgba(0,229,160,0.28);
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
            background:rgba(0,229,160,0.06);
            border:1px solid rgba(0,229,160,0.20);
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
                    background:rgba(0,229,160,0.10);border:1px solid rgba(0,229,160,0.30);
                    border-radius:7px;margin-top:2px;">
                    <span style="font-size:15px">✅</span>
                    <span style="font-size:12px;color:#00805C;font-weight:600">
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


def _render_split_input(supplier: str, total: float) -> tuple[bool, float]:
    """
    Controle opcional de divisão da cobrança. Quando ativado, o admin define o
    percentual do valor absorvido pela empresa; o restante é o que será
    efetivamente cobrado do fornecedor.

    Retorna (split_active, perc_empresa_frac), com a fração em [0.01, 0.99].
    O percentual fica em [1, 99] para manter as duas metades sempre com valor.
    """
    split_active = st.checkbox(
        "➗ Dividir esta cobrança com o fornecedor",
        key=f"split_toggle_{supplier}",
        help="Divide o valor entre o fornecedor e a empresa. A parte do "
             "fornecedor segue para o Histórico de Cobranças; a parte da "
             "empresa é registrada na aba Cobrança Dividida.",
    )
    if not split_active:
        return False, 0.0

    col_pct, col_resume = st.columns([1, 2])
    with col_pct:
        perc_empresa = st.number_input(
            "Percentual absorvido pela empresa (%)",
            min_value=1.0,
            max_value=99.0,
            value=50.0,
            step=5.0,
            format="%.1f",
            key=f"split_perc_{supplier}",
            help="Fração do valor que a empresa assume. O fornecedor é cobrado "
                 "pelo restante. Aplica-se proporcionalmente a valor, minutos e peças.",
        )

    perc_frac        = perc_empresa / 100.0
    valor_empresa    = total * perc_frac
    valor_fornecedor = total - valor_empresa

    with col_resume:
        st.markdown(
            f"""
            <div style="margin-top:1.8rem;font-size:12px;color:{COLORS['text_muted']}">
                Fornecedor será cobrado:
                <strong style="color:#E74C3C">R$ {valor_fornecedor:,.2f}</strong>
                ({100 - perc_empresa:.0f}%) &nbsp;·&nbsp;
                Empresa absorve:
                <strong style="color:#0F86A3">R$ {valor_empresa:,.2f}</strong>
                ({perc_empresa:.0f}%)
            </div>
            """,
            unsafe_allow_html=True,
        )

    return True, perc_frac


def _render_charge_button(
    supplier: str,
    cnpj: str,
    total: float,
    df_records: pd.DataFrame,
    df_display: pd.DataFrame,
    cnpj_valid: bool,
    df_full: pd.DataFrame,
    data_cobranca: date,
    data_vencimento: date,
    dias_para_vencer: int,
    reference_date: date,
    reference_date_end: date,
    split_active: bool = False,
    df_records_empresa: pd.DataFrame | None = None,
) -> None:
    """
    Gerencia o fluxo:
      1. Botão "Pré-visualizar" → abre modal com detalhes
      2. Dentro do modal: "Confirmar e Lançar"
         → gera Excel, salva bd_cobranca, remove fornecedor do df
      3. Estado: "Cobrança lançada" com download disponível

    O estado de lançamento é isolado por fornecedor + Período de Referência,
    para que trocar o período não mostre "já lançado" indevidamente nem
    bloqueie uma nova cobrança do mesmo fornecedor em outro período.
    """
    period_label = (
        reference_date.strftime('%d/%m/%Y')
        if reference_date == reference_date_end
        else f"{reference_date.strftime('%d/%m/%Y')} até {reference_date_end.strftime('%d/%m/%Y')}"
    )
    charge_id      = f"{supplier}_{reference_date.isoformat()}_{reference_date_end.isoformat()}"
    charge_key     = f"charge_confirmed_{charge_id}"
    charge_doc_key = f"charge_doc_{charge_id}"

    # ── Processar confirmação vinda do modal ──────────────────────────────────
    if st.session_state.pop("_preview_confirmed", False):
        if not is_admin():
            st.error("Acesso negado: apenas administradores podem lançar cobranças.")
            return
        try:
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
                    data_cobranca=data_cobranca,
                    data_vencimento=data_vencimento,
                    dias_para_vencer=dias_para_vencer,
                )

                # 3. Persiste a cobrança numa única transação: reivindica (apaga)
                #    os registros do fornecedor no Período de Referência e grava a
                #    cobrança em historico_cobrancas — mais a metade da empresa em
                #    tb_divida_dividida, com o mesmo COD_LANCAMENTO, quando há
                #    divisão. Se outra sessão já lançou esta cobrança, não há
                #    registros a reivindicar e nada é gravado.
                cod_lancamento = launch_charge(
                    supplier=supplier,
                    cnpj=cnpj,
                    df_records=df_export,
                    data_cobranca=data_cobranca,
                    data_vencimento=data_vencimento,
                    reference_date=reference_date,
                    reference_date_end=reference_date_end,
                    df_empresa=(
                        df_records_empresa
                        if split_active and df_records_empresa is not None
                        else None
                    ),
                )
        except ChargeAlreadyLaunchedError as exc:
            st.warning(f"⚠️ {exc}")
            return
        except DatabaseUnavailableError as exc:
            st.error(f"⚠️ {exc}")
            return
        except Exception:
            logger.exception("Falha ao lançar cobrança para fornecedor %s", supplier)
            st.error(
                "⚠️ Não foi possível concluir o lançamento da cobrança. "
                "Nenhuma alteração foi salva. Tente novamente ou contate o suporte."
            )
            return

        now_str = date.today().strftime("%d/%m/%Y")
        st.session_state[charge_key]                 = True
        st.session_state[charge_doc_key]             = excel_bytes
        st.session_state[f"charge_html_{charge_id}"] = html_page
        st.session_state[f"charge_time_{charge_id}"] = now_str
        st.session_state[f"charge_cod_{charge_id}"]  = cod_lancamento
        st.rerun()

    already_launched = st.session_state.get(charge_key, False)

    if already_launched:
        # ── Estado: cobrança lançada ──────────────────────────────────────────
        launched_at = st.session_state.get(f"charge_time_{charge_id}", "")
        cod_lancamento = st.session_state.get(f"charge_cod_{charge_id}", "")
        st.markdown(
            f"""
            <div style="
                background:rgba(0,229,160,0.12);
                border:1px solid rgba(0,229,160,0.35);
                border-radius:10px; padding:14px 18px;
            ">
                <span style="font-size:14px;font-weight:600;color:#00805C">
                    ✅ Cobrança lançada com sucesso
                </span>
                <p style="font-size:12px;color:{COLORS['text_muted']};margin:4px 0 0">
                    Fornecedor: <strong>{supplier}</strong> —
                    Período de Referência: <strong>{period_label}</strong> —
                    Emitida em: {launched_at} —
                    Código: <code style="color:#534AB7;font-weight:700">{cod_lancamento}</code> —
                    Registros removidos da planilha ativa e salvos em
                    <code style="color:#0D1B17">dataset/bd_cobranca.xlsx</code>
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
                    label="Baixar Documento de Cobranca (Excel)",
                    data=st.session_state[charge_doc_key],
                    file_name=f"cobranca_{supplier.replace(' ', '_')}_{reference_date.isoformat()}_{reference_date_end.isoformat()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_after_{charge_id}",
                    use_container_width=True,
                )
        with col_pdf_preview:
            html_page = st.session_state.get(f"charge_html_{charge_id}", "")
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
    background: rgba(0,229,160,0.15);
    color:#00805C;
    border: 1px solid rgba(0,229,160,0.35);
  }}
  .btn:hover {{
    background: rgba(0,229,160,0.28);
    border-color: rgba(0,229,160,0.6);
  }}
  .btn:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
<button class="btn" onclick="openPreview()">Previa / Imprimir PDF</button>
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
        if st.button(
            "↺ Relançar / Emitir Novo Documento",
            key=f"relaunch_{charge_id}",
            use_container_width=True,
            disabled=not is_admin(),
            help=None if is_admin() else "Apenas administradores podem relançar cobranças.",
        ):
            st.session_state.pop(charge_key, None)
            st.session_state.pop(charge_doc_key, None)
            st.session_state.pop(f"charge_html_{charge_id}", None)
            st.session_state.pop(f"charge_time_{charge_id}", None)
            st.session_state.pop(f"charge_cod_{charge_id}", None)
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
            "Pre-visualizar Cobranca",
            use_container_width=True,
            key=f"preview_{charge_id}",
        ):
            _show_preview_dialog(
                supplier=supplier,
                cnpj=cnpj,
                total=total,
                df_display=df_display,
                n_records=n_records,
                n_orders=n_orders,
                data_cobranca=data_cobranca,
                data_vencimento=data_vencimento,
                dias_para_vencer=dias_para_vencer,
            )

    with col_launch:
        if st.button(
            f"🚀 Lançar — R$ {total:,.2f}",
            type="primary",
            use_container_width=True,
            key=f"launch_{charge_id}",
            disabled=not is_admin(),
            help=None if is_admin() else "Apenas administradores podem lançar cobranças.",
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
            data_cobranca=data_cobranca,
            data_vencimento=data_vencimento,
            dias_para_vencer=dias_para_vencer,
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
    background: rgba(0,229,160,0.15);
    color:#00805C;
    border: 1px solid rgba(0,229,160,0.35);
  }}
  .btn:hover {{
    background: rgba(0,229,160,0.28);
    border-color: rgba(0,229,160,0.6);
  }}
  .btn:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
<button class="btn" onclick="openPreview()">Previa / Imprimir PDF</button>
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
                <span style="display:block;font-size:9.5px;color:#4A5752;margin-top:2px">
                    Use Pré-visualizar ou Prévia / Imprimir para revisar.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )


# (histórico movido para pages/3_Historico_Cobranca.py — v12)
