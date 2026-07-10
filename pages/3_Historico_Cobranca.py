# -*- coding: utf-8 -*-
"""
Pagina: Historico de Cobrancas — consolida em abas as 4 telas de cobranca:
  1) Historico de Cobrancas  (bd_cobranca.xlsx / tabela cobrancas)
  2) Cobranca de Fornecedores
  3) Pagamentos Concluidos   (tabela pagamentos_concluidos)
  4) Devolucao               (tabela devolucoes)

CHANGELOG v15.0:
  - Adicionada aba Devolucao: a opcao de status "Contestado" foi substituida
    por "Devolucao" (a oficina fornecedora opta por consertar as pecas com
    defeito em vez de pagar o desconto). Ao marcar um lancamento como
    Devolucao ele sai do Historico e e movido para a tabela devolucoes,
    seguindo a mesma regra ja usada para "Pago" -> pagamentos_concluidos.

CHANGELOG v14.0:
  - Consolidacao: Cobranca de Fornecedores e Pagamentos Concluidos deixaram
    de ser paginas proprias na sidebar e passaram a ser abas (st.tabs) desta
    pagina, reduzindo a navegacao multi-pagina. Cada aba calcula seus proprios
    totais/KPIs de forma independente, portanto os cards sempre refletem os
    dados da aba selecionada.

CHANGELOG v13.0:
  - Adicionado: campo STATUS_COBRANCA (Pendente / Pago / Contestado)
  - Adicionado: edição inline de status na tabela, salvo direto no xlsx
  - Adicionado: filtro por status na sidebar
  - Adicionado: badge colorido por status na tabela
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Historico de Cobranças",
    page_icon="🗃️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config.settings import COLS, COLORS
from src.data.cobranca_history import (
    HISTORY_LABELS,
    STATUS_OPTIONS,
    load_history,
    update_lancamento_status,
    migrate_paid_to_payments,
    migrate_contestado_to_devolucao,
    generate_history_xlsx_bytes,
    generate_single_charge_xlsx_bytes,
    group_charges,
    status_badge_html,
    situacao_badge_html,
    payment_punctuality,
)
from src.data.payment_history import load_payments, generate_payments_xlsx_bytes
from src.data.devolucao_history import load_devolucoes, generate_devolucoes_xlsx_bytes
from src.ui.cobranca import render_cobranca_page
import base64
import streamlit.components.v1 as components
from src.ui.preview import _generate_historico_html
from src.auth.session import require_login, render_user_sidebar, is_admin
from src.ui.error_boundary import page_guard

# ── CSS global ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] > .main { background: #FAFCFB; }
    [data-testid="stMain"]                      { background: #FAFCFB; }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }
    [data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 1px solid rgba(0,0,0,0.06);
    }
    [data-testid="stSidebar"] label { color: #4A5752 !important; font-size: 13px !important; }
    .stButton > button {
        height: 38px !important;
        min-width: 160px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 0 20px !important;
        background: rgba(0,229,160,0.15) !important;
        color:#00805C !important;
        border: 1px solid rgba(0,229,160,0.35) !important;
        transition: all .15s ease !important;
    }
    .stButton > button:hover {
        background: rgba(0,229,160,0.28) !important;
        border-color: rgba(0,229,160,0.6) !important;
    }
    .stButton > button[kind="primary"] {
        background: rgba(194,57,43,0.85) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(194,57,43,0.6) !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        height: auto !important;
        min-width: 0 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: rgba(194,57,43,1.0) !important;
    }
    [data-testid="stDownloadButton"] > button {
        height: 38px !important;
        min-width: 160px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 0 20px !important;
    }
    [data-testid="stExpander"] {
        background: rgba(0,0,0,0.02) !important;
        border: 1px solid rgba(0,0,0,0.07) !important;
        border-radius: 10px !important;
    }
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    hr { border-color: rgba(0,0,0,0.06) !important; }

    /* ── Abas (Histórico / Cobrança / Pagamentos / Devolução) ── */
    .stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid rgba(0,184,132,0.20); gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        color: #4A5752 !important;
        font-weight: 600 !important;
        font-size: 13.5px !important;
        padding: 10px 16px !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #00805C !important; }
    .stTabs [data-baseweb="tab-highlight"] { background: #00B884 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Ordem das colunas na tabela (aba Histórico) ───────────────────────────────
_ORDERED_COLS = [
    "COD_LANCAMENTO",
    "DATA_COBRANCA",
    "DATA_VENCIMENTO",
    "DATA_PAGAMENTO",
    COLS["supplier"],
    "CNPJ_FORNECEDOR",
    COLS["status"],          # <-- novo campo STATUS
    COLS["order"],
    COLS["date"],
    COLS["quantity"],
    COLS["defect"],
    COLS["real_cut"],
    COLS["minutes"],
    COLS["value_brl"],
]

# ── Ordem das colunas na tabela (aba Pagamentos — sem "Status", sempre "Pago") ─
_PAG_ORDERED_COLS = [
    "COD_LANCAMENTO",
    "DATA_COBRANCA",
    "DATA_VENCIMENTO",
    "DATA_PAGAMENTO",
    COLS["supplier"],
    "CNPJ_FORNECEDOR",
    COLS["order"],
    COLS["date"],
    COLS["quantity"],
    COLS["defect"],
    COLS["real_cut"],
    COLS["minutes"],
    COLS["value_brl"],
]


# ══════════════════════════════════════════════════════════════════════════════
# Cards KPI
# ══════════════════════════════════════════════════════════════════════════════

def _kpi_card(col, icon: str, label: str, value: str, accent: str) -> None:
    with col:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(160deg, #FFFFFF 0%, #F2F7F5 100%);
                border: 1px solid {accent}40;
                border-top: 2px solid {accent};
                border-radius: 12px;
                padding: 0.9rem 0.75rem 0.8rem;
                box-shadow: 0 0 22px {accent}18, 0 2px 8px rgba(0,0,0,0.35);
            ">
                <div style="font-size:9.5px; color:#0D1B17;
                            text-transform:uppercase; letter-spacing:0.6px;
                            margin-bottom:6px; font-weight:600">
                    <span style="color:{accent}; margin-right:5px">{icon}</span>{label}
                </div>
                <div style="font-size:19px; font-weight:700; color:#0D1B17;
                            letter-spacing:-0.4px; white-space:nowrap;
                            overflow:hidden; text-overflow:ellipsis">
                    {value}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tabela de extrato (resumo por lançamento) + popup de detalhes — aba Histórico
# ══════════════════════════════════════════════════════════════════════════════

def _render_simple_table(df: pd.DataFrame, left_cols: frozenset = frozenset(), height: int = 420) -> None:
    """Renderiza um DataFrame como tabela HTML estilizada (cabeçalho fixo, zebra, badges)."""
    headers = list(df.columns)

    TH = (
        "padding:11px 14px;text-align:center;color:#FFFFFF;font-weight:600;"
        "font-size:10px;text-transform:uppercase;letter-spacing:0.9px;"
        "background:#00805C;border-bottom:2px solid #00B884;"
        "white-space:nowrap;position:sticky;top:0;z-index:1;"
    )
    TH_L = TH + "text-align:left;"

    head_html = "".join(
        f'<th style="{TH_L if h in left_cols else TH}">✦ {h}</th>' for h in headers
    )

    def _make_cell(h, val, row_bg):
        align = "text-align:left;" if h in left_cols else "text-align:center;"
        base_td = (
            f"padding:9px 14px;font-size:12.5px;color:#0D1B17;"
            f"border-bottom:1px solid rgba(0,229,160,0.12);"
            f"{align}{row_bg}"
        )
        return f'<td style="{base_td}">{val}</td>'

    rows_html = "".join(
        "<tr>" + "".join(
            _make_cell(h, row[h], "background:#FFFFFF;" if i % 2 == 1 else "background:#F2F7F5;")
            for h in headers
        ) + "</tr>"
        for i, (_, row) in enumerate(df.iterrows())
    )

    table_html = f"""
    <style>
      .nv-table-wrap::-webkit-scrollbar {{ width:6px; height:6px; }}
      .nv-table-wrap::-webkit-scrollbar-track {{ background:#FFFFFF; border-radius:3px; }}
      .nv-table-wrap::-webkit-scrollbar-thumb {{ background:rgba(0,229,160,0.45); border-radius:3px; }}
      .nv-table-wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(0,229,160,0.70); }}
      .nv-table-wrap tr:hover td {{ background:rgba(0,229,160,0.14)!important; transition:background 0.15s; }}
      .badge-status {{
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        display: inline-block;
      }}
      .status-pago {{ background: #00E5A0 !important; color: #FFFFFF !important; }}
      .status-pendente {{ background: #EF9F27 !important; color:#FFFFFF !important; }}
      .status-contestado {{ background: #D85A30 !important; color: #FFFFFF !important; }}
      .status-devolucao {{ background: #0F86A3 !important; color: #FFFFFF !important; }}
    </style>
    <div class="nv-table-wrap" style="
        max-height:{height}px; overflow:auto; border-radius:12px;
        border:1px solid rgba(0,229,160,0.32);
        border-top:2px solid #00B884;
        background:#F2F7F5;
        box-shadow:0 0 22px rgba(0,229,160,0.10);
    ">
      <table style="width:100%;border-collapse:collapse;min-width:900px;">
        <thead><tr>{head_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


def _build_extrato_df(charge_groups: list[dict]) -> pd.DataFrame:
    """Converte a lista de grupos (uma cobrança por linha) num DataFrame de extrato."""
    rows = [
        {
            "Código": g["cod"],
            "Fornecedor": g["fornecedor"],
            "CNPJ": g["cnpj"],
            "Data Cobrança": g["data_cobranca"],
            "Vencimento": g["data_vencimento"],
            "Situação": situacao_badge_html(g["status"], g["data_vencimento"], g["data_pagamento"]),
            "Status": status_badge_html(g["status"]),
            "Itens": g["n_itens"],
            "Valor Total": f"R$ {g['valor_total']:,.2f}",
        }
        for g in charge_groups
    ]
    return pd.DataFrame(rows)


def _render_print_button(html_content: str) -> None:
    """Botão que abre um HTML de impressão em nova aba (padrão de 'PDF' usado no app)."""
    html_b64 = base64.b64encode(html_content.encode("utf-8")).decode()
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
    width: 100%; min-width: 160px; height: 38px; border-radius: 6px; cursor: pointer;
    font-size: 14px; font-weight: 500;
    transition: all .15s ease;
    background: rgba(0,229,160,0.15);
    color:#00805C;
    border: 1px solid rgba(0,229,160,0.35);
    padding: 0 20px;
  }}
  .btn:hover {{
    background: rgba(0,229,160,0.28);
    border-color: rgba(0,229,160,0.6);
  }}
  .btn:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
<button class="btn" onclick="openPreview()">🖨️&nbsp; Prévia / Imprimir PDF</button>
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
      alert("Não foi possível abrir a prévia. Permita popups para este site.");
    }}
  }}
</script>
</body>
</html>""",
        height=38,
        scrolling=False,
    )


@st.dialog("🧾 Detalhes do Extrato", width="large")
def _show_extrato_dialog(cod_lancamento: str, df_source: pd.DataFrame) -> None:
    """Popup com todos os itens de um COD_LANCAMENTO e opções de download (Excel / PDF)."""
    cod_label     = HISTORY_LABELS.get("COD_LANCAMENTO",  "Código")
    sup_label     = HISTORY_LABELS.get(COLS["supplier"],  "Fornecedor")
    cnpj_label    = HISTORY_LABELS.get("CNPJ_FORNECEDOR", "CNPJ")
    dte_label     = HISTORY_LABELS.get("DATA_COBRANCA",   "Data Cobrança")
    venc_label    = HISTORY_LABELS.get("DATA_VENCIMENTO", "Data Vencimento")
    status_label  = HISTORY_LABELS.get(COLS["status"],    "Status")
    val_label     = HISTORY_LABELS.get(COLS["value_brl"], "Valor (R$)")
    ord_label     = HISTORY_LABELS.get(COLS["order"],     "OM")
    qty_label     = HISTORY_LABELS.get(COLS["quantity"],  "Qtd")
    min_label     = HISTORY_LABELS.get(COLS["minutes"],   "Min. Gerados")
    remonte_label = HISTORY_LABELS.get(COLS["defect"],    "Remonte")
    rc_label      = HISTORY_LABELS.get(COLS["real_cut"],  "Real Cortado")
    prod_label    = HISTORY_LABELS.get(COLS["date"],      "Data Produção")

    df_item = df_source[df_source[cod_label] == cod_lancamento].copy()
    if df_item.empty:
        st.warning("Nenhum item encontrado para este código.")
        return

    primeira    = df_item.iloc[0]
    valor_total = pd.to_numeric(df_item[val_label], errors="coerce").sum()

    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px;
                    padding:12px 16px;margin-bottom:14px;border-radius:10px;
                    background:#F2F7F5;border:1px solid rgba(0,229,160,0.25)">
            <div>
                <div style="font-size:15px;font-weight:700;color:#0D1B17">{primeira[sup_label]}</div>
                <div style="font-size:12px;color:#4A5752">CNPJ: {primeira[cnpj_label]}</div>
            </div>
            <div style="text-align:right;font-size:12px;color:#4A5752">
                <div>Código: <strong style="font-family:Consolas,monospace;color:#534AB7">{cod_lancamento}</strong></div>
                <div>Cobrança: {primeira[dte_label]} &nbsp;·&nbsp; Vencimento: {primeira[venc_label]}</div>
                <div style="margin-top:4px">{status_badge_html(primeira[status_label])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    item_cols = [c for c in (ord_label, prod_label, qty_label, remonte_label, rc_label, min_label, val_label)
                 if c in df_item.columns]
    df_display_item = df_item[item_cols].copy()
    if val_label in df_display_item.columns:
        df_display_item[val_label] = df_display_item[val_label].apply(
            lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else ""
        )
    if min_label in df_display_item.columns:
        df_display_item[min_label] = df_display_item[min_label].apply(
            lambda v: f"{float(v):,.2f}" if pd.notna(v) else ""
        )
    if qty_label in df_display_item.columns:
        df_display_item[qty_label] = df_display_item[qty_label].apply(
            lambda v: f"{int(float(v)):,}" if pd.notna(v) else ""
        )
    if ord_label in df_display_item.columns:
        df_display_item[ord_label] = df_display_item[ord_label].apply(
            lambda v: f"{int(float(v))}" if pd.notna(v) else ""
        )
    if rc_label in df_display_item.columns:
        df_display_item[rc_label] = df_display_item[rc_label].apply(
            lambda v: f"{int(float(v)):,}" if pd.notna(v) else ""
        )

    _render_simple_table(df_display_item, left_cols=frozenset({remonte_label}), height=300)

    st.markdown(
        f"<div style='text-align:right;font-size:14px;font-weight:700;color:#0D1B17;margin:10px 0'>"
        f"Total: R$ {valor_total:,.2f}</div>",
        unsafe_allow_html=True,
    )

    col_xlsx, col_pdf = st.columns(2)
    with col_xlsx:
        xlsx_bytes = generate_single_charge_xlsx_bytes(cod_lancamento)
        if xlsx_bytes:
            st.download_button(
                "⬇️  Baixar Excel",
                data=xlsx_bytes,
                file_name=f"extrato_{cod_lancamento}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_extrato_xlsx_{cod_lancamento}",
                use_container_width=True,
            )
        else:
            st.button(
                "⬇️  Baixar Excel", disabled=True, use_container_width=True,
                key=f"dl_extrato_xlsx_disabled_{cod_lancamento}",
            )

    with col_pdf:
        totals_item = dict(
            n_records=len(df_item),
            total_minutes=pd.to_numeric(df_item[min_label], errors="coerce").sum() if min_label in df_item.columns else 0.0,
            total_value=float(valor_total) if pd.notna(valor_total) else 0.0,
            total_pieces=int(pd.to_numeric(df_item[qty_label], errors="coerce").sum()) if qty_label in df_item.columns else 0,
            n_orders=df_item[ord_label].nunique() if ord_label in df_item.columns else 0,
            n_cobrancas=1,
        )
        html_item = _generate_historico_html(
            df_item.drop(columns=["_orig_idx"], errors="ignore"),
            totals_item,
            f"Código: {cod_lancamento}",
        )
        _render_print_button(html_item)


# ══════════════════════════════════════════════════════════════════════════════
# Aba: Histórico de Cobranças
# ══════════════════════════════════════════════════════════════════════════════

def _render_historico_tab() -> None:
    # ── Cabeçalho ─────────────────────────────────────────────────────────────
   # st.markdown(
   #     f"""
   #     <div style="padding:0.5rem 0 1.2rem;margin-bottom:0.6rem">
   #         <p style="color:{COLORS['text_muted']};font-size:13px;margin:0">
   #             Registro acumulado de todas as cobranças confirmadas, exceto as já pagas
   #             — essas ficam na aba <strong>Pagamentos Concluídos</strong> — e as
   #             devolvidas para conserto, que ficam na aba <strong>Devolução</strong>.
   #             Edite o status diretamente no painel abaixo.
   #         </p>
   #     </div>
   #     """,
   #     unsafe_allow_html=True,
   # )

    # ── Carregar histórico ────────────────────────────────────────────────────
    df_hist = load_history()

    if df_hist is None or df_hist.empty:
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;
                        justify-content:center;min-height:50vh;text-align:center;gap:14px">
                <div style="font-size:52px;opacity:0.18">🗃️</div>
                <p style="font-size:20px;font-weight:600;
                          color:{COLORS['text_primary']};margin:0">
                    Nenhum histórico encontrado
                </p>
                <p style="font-size:13px;color:{COLORS['text_subtle']};
                          margin:0;max-width:400px;line-height:1.7">
                    O histórico será criado automaticamente ao confirmar
                    a primeira cobrança na aba
                    <strong style="color:{COLORS['text_primary']}">
                        Cobrança de Fornecedores
                    </strong>.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Manter índice original para rastrear posição no xlsx
    df_hist = df_hist.reset_index(drop=True)
    df_hist["_orig_idx"] = df_hist.index

    # ── Preparar colunas visíveis ─────────────────────────────────────────────
    cols_avail = [c for c in _ORDERED_COLS if c in df_hist.columns]
    df_view    = df_hist[cols_avail + ["_orig_idx"]].copy()
    df_view.rename(columns=HISTORY_LABELS, inplace=True)

    status_label = HISTORY_LABELS.get(COLS["status"], "Status")
    val_label    = HISTORY_LABELS.get(COLS["value_brl"], "Valor (R$)")
    min_label    = HISTORY_LABELS.get(COLS["minutes"],   "Min. Gerados")
    qty_label    = HISTORY_LABELS.get(COLS["quantity"],  "Qtd")
    ord_label    = HISTORY_LABELS.get(COLS["order"],     "OM")
    sup_label    = HISTORY_LABELS.get(COLS["supplier"],  "Fornecedor")
    dte_label    = HISTORY_LABELS.get("DATA_COBRANCA",   "Data Cobrança")
    venc_label   = HISTORY_LABELS.get("DATA_VENCIMENTO", "Data Vencimento")
    pag_label    = HISTORY_LABELS.get("DATA_PAGAMENTO",  "Data Pagamento")
    cnpj_label   = HISTORY_LABELS.get("CNPJ_FORNECEDOR", "CNPJ")
    cod_label    = HISTORY_LABELS.get("COD_LANCAMENTO",  "Código")

    for col in (val_label, min_label, qty_label):
        if col in df_view.columns:
            df_view[col] = pd.to_numeric(df_view[col], errors="coerce")

    # ── Filtros ───────────────────────────────────────────────────────────────
    date_from = date_to = None
    with st.expander("🔍 Filtros", expanded=False):
        col_from, col_to, col_search = st.columns([1, 1, 2])

        if dte_label in df_view.columns:
            try:
                dates_parsed = pd.to_datetime(df_view[dte_label], format="%d/%m/%Y", errors="coerce")
                min_date = dates_parsed.dropna().min().date()
                max_date = dates_parsed.dropna().max().date()
            except Exception:
                min_date = date.today() - timedelta(days=365)
                max_date = date.today()

            with col_from:
                date_from = st.date_input(
                    "De", value=min_date, min_value=min_date, max_value=max_date,
                    key="hist_date_from",format="DD/MM/YYYY"
                )
            with col_to:
                date_to = st.date_input(
                    "Até", value=max_date, min_value=min_date, max_value=max_date,
                    key="hist_date_to",format="DD/MM/YYYY"
                )

        with col_search:
            search_term = st.text_input(
                "Fornecedor, CNPJ ou Código",
                placeholder="Digite nome, CNPJ ou código…",
                key="hist_search",
            )

        col_status, col_clear = st.columns([3, 1])
        with col_status:
            status_filter = st.multiselect(
                "Status",
                options=STATUS_OPTIONS,
                default=STATUS_OPTIONS,
                key="hist_status_filter",
            )
        with col_clear:
            st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
            if st.button("↺ Limpar Filtros", key="hist_clear", use_container_width=True):
                for k in ("hist_date_from", "hist_date_to", "hist_search", "hist_status_filter"):
                    st.session_state.pop(k, None)
                st.rerun()

    search_term = st.session_state.get("hist_search", "")
    status_filter = st.session_state.get("hist_status_filter", STATUS_OPTIONS)

    # ── Aplicar filtros ───────────────────────────────────────────────────────
    df_filtered = df_view.copy()
    filters_parts = []

    if date_from and date_to and dte_label in df_filtered.columns:
        parsed = pd.to_datetime(df_filtered[dte_label], format="%d/%m/%Y", errors="coerce")
        mask   = (parsed.dt.date >= date_from) & (parsed.dt.date <= date_to)
        df_filtered = df_filtered[mask]
        filters_parts.append(
            f"Período: {date_from.strftime('%d/%m/%Y')} a {date_to.strftime('%d/%m/%Y')}"
        )
    else:
        filters_parts.append("Período: todos")

    if search_term and search_term.strip():
        term  = search_term.strip().lower()
        masks = [
            df_filtered[col].astype(str).str.lower().str.contains(term, na=False)
            for col in (sup_label, cnpj_label, cod_label)
            if col in df_filtered.columns
        ]
        if masks:
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m
            df_filtered = df_filtered[combined]
        filters_parts.append(f"Busca: \"{search_term.strip()}\"")
    else:
        filters_parts.append("Fornecedor/CNPJ/Código: todos")

    if status_filter and status_label in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[status_label].isin(status_filter)]
        filters_parts.append(f"Status: {', '.join(status_filter)}")
    else:
        filters_parts.append("Status: todos")

    filters_desc = "   |   ".join(filters_parts)

    # ── Calcular totais ───────────────────────────────────────────────────────
    total_value   = df_filtered[val_label].sum() if val_label in df_filtered.columns else 0.0
    total_minutes = df_filtered[min_label].sum() if min_label in df_filtered.columns else 0.0
    total_pieces  = int(df_filtered[qty_label].sum()) if qty_label in df_filtered.columns else 0
    n_orders      = df_filtered[ord_label].nunique() if ord_label in df_filtered.columns else 0
    # Cobranças únicas: contadas pelo Código de Lançamento — um mesmo CNPJ pode
    # ter mais de uma cobrança (cada uma com seu Código), portanto contar por
    # código evita duplicar e reflete o nº real de cobranças realizadas.
    n_cobrancas   = df_filtered[cod_label].nunique() if cod_label in df_filtered.columns else 0
    n_records     = len(df_filtered)

    totals = dict(
        n_records=n_records,
        total_minutes=total_minutes,
        total_value=total_value,
        total_pieces=total_pieces,
        n_orders=n_orders,
        n_cobrancas=n_cobrancas,
    )

    # ── 6 Cards KPI ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _kpi_card(c1, "🧵", "PEÇAS COM DEFEITO",    f"{total_pieces:,}",         "#0F86A3")
    _kpi_card(c2, "📋", "TOTAL DEFEITOS",        str(n_records),              "#00B884")
    _kpi_card(c3, "⏱️", "TOTAL MINUTOS",         f"{total_minutes:,.0f} min", "#00E5A0")
    _kpi_card(c4, "💰", "VALOR TOTAL",           f"R$ {total_value:,.2f}",    "#E24B4A")
    _kpi_card(c5, "📦", "ORDENS ÚNICAS (OM)",    str(n_orders),               "#EF9F27")
    _kpi_card(c6, "🧾", "COBRANÇAS REALIZADAS",  str(n_cobrancas),            "#7B5EA7")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Badge de filtros ativos
    st.markdown(
        f"""
        <div style="
            font-size:11px; color:{COLORS['text_subtle']};
            background:rgba(0,229,160,0.08);
            border:1px solid rgba(0,229,160,0.18);
            border-radius:6px; padding:6px 14px; margin-bottom:12px;
            display:inline-block;
        ">
            ⚙️ {filters_desc} &nbsp;·&nbsp; {n_records} registro(s)
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabela de Extrato (resumo por lançamento) ─────────────────────────────
    # Uma linha por COD_LANCAMENTO, não por item — os detalhes completos ficam
    # disponíveis no popup "Ver Detalhes" (busca + seleção abaixo).
    charge_groups = group_charges(
        df_filtered, cod_label, sup_label, cnpj_label, dte_label,
        venc_label, pag_label, status_label, val_label,
    )
    charge_opts = [
        (
            f"{g['fornecedor']} | Código: {g['cod']} | "
            f"R$ {g['valor_total']:,.2f} | {g['n_itens']} item(ns) | {g['data_cobranca']}",
            g["cod"], g["status"], g["data_vencimento"], g["data_pagamento"],
        )
        for g in charge_groups
    ]

    if charge_groups:
        _render_simple_table(
            _build_extrato_df(charge_groups),
            left_cols=frozenset({"Fornecedor"}),
            height=440,
        )
    else:
        st.info("Nenhum extrato encontrado para os filtros atuais.")

    # ── Buscar + abrir extrato específico em popup ────────────────────────────
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    col_sel, col_view = st.columns([3, 1])
    if charge_opts:
        selected_detail = col_sel.selectbox(
            "Ver detalhes do extrato",
            options=charge_opts,
            format_func=lambda x: f"[{x[2]}] {x[0]}",
            key="select_charge_detail",
        )
        with col_view:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("👁️  Ver Detalhes", use_container_width=True, key="btn_view_extrato_detail"):
                _show_extrato_dialog(selected_detail[1], df_filtered)
    else:
        col_sel.caption("Nenhum extrato disponível para os filtros atuais.")

    # ── Painel de Controle de Status ──────────────────────────────────────────
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    with st.expander("📝 Atualizar Status de Lançamento", expanded=True):
        _pode_editar_status = is_admin()
        st.caption(
            "Uma cobrança pode ter vários itens (um por defeito/OM) — todos compartilham "
            "o mesmo Código. A alteração abaixo sempre vale para o lançamento inteiro. "
            "Ao marcar como **Pago**, a cobrança sai deste histórico e passa para a aba "
            "**Pagamentos Concluídos**. Ao marcar como **Devolução** — quando a oficina "
            "fornecedora opta por consertar as peças em vez de pagar o desconto — a "
            "cobrança sai deste histórico e passa para a aba **Devolução**."
        )
        if not _pode_editar_status:
            st.caption("🔒 Apenas administradores podem alterar o status de um lançamento.")
        col_rec, col_st, col_pag, col_act = st.columns([2, 1, 1, 1])

        if charge_opts:
            selected_opt = col_rec.selectbox(
                "Selecionar Lançamento de Cobrança",
                options=charge_opts,
                format_func=lambda x: f"[{x[2]}] {x[0]}",
                key="select_charge_to_update"
            )

            curr_st = selected_opt[2]
            curr_pag = selected_opt[4]
            status_idx = STATUS_OPTIONS.index(curr_st) if curr_st in STATUS_OPTIONS else 0

            new_st = col_st.selectbox(
                "Alterar Status para",
                options=STATUS_OPTIONS,
                index=status_idx,
                key="new_status_select",
                disabled=not _pode_editar_status,
            )

            # ── Data do Pagamento: só faz sentido quando o status é "Pago".
            # É sempre informada manualmente pelo usuário (não é automática) ──
            data_pagamento_input = None
            with col_pag:
                if new_st == "Pago":
                    _default_pag = pd.to_datetime(curr_pag, format="%d/%m/%Y", errors="coerce")
                    _default_pag = _default_pag.date() if pd.notna(_default_pag) else date.today()
                    data_pagamento_input = st.date_input(
                        "Data do Pagamento",
                        value=_default_pag,
                        format="DD/MM/YYYY",
                        key="data_pagamento_input",
                        help="Data em que o pagamento foi efetivamente realizado. "
                             "Usada para indicar se foi pago no prazo ou com atraso.",
                        disabled=not _pode_editar_status,
                    )
                else:
                    st.markdown(
                        f"<div style='margin-top:1.8rem;font-size:11px;color:{COLORS.get('text_subtle', '#7C8985')}'>"
                        "Disponível ao marcar como Pago</div>",
                        unsafe_allow_html=True,
                    )

            if col_act.button(
                "💾 Salvar Alteração",
                use_container_width=True,
                key="btn_update_status_db",
                disabled=not _pode_editar_status,
                help=None if _pode_editar_status else "Apenas administradores podem alterar o status.",
            ):
                cod_sel = selected_opt[1]
                ok = update_lancamento_status(cod_sel, new_st, data_pagamento=data_pagamento_input)
                if ok:
                    if new_st == "Pago":
                        st.success(
                            f"✅ Cobrança paga com sucesso! Código **{cod_sel}** — "
                            "consulte os detalhes na aba **Pagamentos Concluídos**."
                        )
                    elif new_st == "Devolução":
                        st.success(
                            f"🔄 Cobrança movida para devolução! Código **{cod_sel}** — "
                            "consulte os detalhes na aba **Devolução**."
                        )
                    else:
                        st.success(f"Status atualizado para {new_st} com sucesso!")
                    st.rerun()
                else:
                    st.error("Erro ao atualizar status.")
        else:
            st.info("Nenhum registro encontrado para atualizar.")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    btn_save, btn_dl, btn_pdf, _sp = st.columns([1, 1, 1, 2])

    with btn_save:
        # Botão placeholder para manter alinhamento
        st.button("💾  Salvar alterações", key="btn_save_status", use_container_width=True, disabled=True, help="Status agora é salvo automaticamente pelo painel acima.")

    # ── Botões de exportação ─────────────────────────────────────────────────
    with btn_dl:
        _xlsx_bytes = generate_history_xlsx_bytes() if n_records > 0 else None
        if _xlsx_bytes:
            st.download_button(
                label="⬇️  Baixar Excel",
                data=_xlsx_bytes,
                file_name=f"bd_cobranca_{date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_hist_excel",
                use_container_width=True,
            )
        else:
            st.button("⬇️  Baixar Excel", disabled=True, use_container_width=True)

    with btn_pdf:
        if n_records > 0:
            html_hist = _generate_historico_html(df_filtered, totals, filters_desc)
            _render_print_button(html_hist)
        else:
            st.button(
                "🖨️  Prévia / Imprimir PDF", disabled=True,
                use_container_width=True,
                help="Nenhum registro para exportar.",
            )


# ══════════════════════════════════════════════════════════════════════════════
# Aba: Cobrança de Fornecedores
# ══════════════════════════════════════════════════════════════════════════════

def _render_cobranca_tab() -> None:
    if "df" not in st.session_state:
        st.markdown(
            f"""
            <div style="
                display:flex; flex-direction:column; align-items:center;
                justify-content:center; min-height:50vh; text-align:center; gap:14px;
            ">
                <div style="font-size:48px; opacity:0.18">📂</div>
                <p style="font-size:18px;font-weight:600;
                          color:{COLORS['text_primary']};margin:0">
                    Base principal não encontrada
                </p>
                <p style="font-size:13px;color:{COLORS['text_subtle']};
                          margin:0;max-width:400px;line-height:1.7">
                    Acesse a página
                    <strong style="color:{COLORS['text_primary']}">
                        Análise de Defeitos
                    </strong>
                    e faça a carga inicial da planilha histórica.<br>
                    A base será salva automaticamente e carregada
                    em todos os acessos futuros.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    render_cobranca_page(st.session_state["df"])


# ══════════════════════════════════════════════════════════════════════════════
# Card KPI genérico (compartilhado pelas abas Pagamentos Concluídos e Devolução)
# ══════════════════════════════════════════════════════════════════════════════

def _metric_kpi_card(col, icon: str, label: str, value: str, accent: str) -> None:
    with col:
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(160deg, #FFFFFF 0%, #F2F7F5 100%);
                border: 1px solid {accent}40;
                border-top: 2px solid {accent};
                border-radius: 12px;
                padding: 1rem 1.2rem 0.9rem;
                box-shadow: 0 0 22px {accent}18, 0 2px 8px rgba(0,0,0,0.35);
            ">
                <div style="font-size:10px; color:#0D1B17;
                            text-transform:uppercase; letter-spacing:0.9px;
                            margin-bottom:6px; font-weight:600">
                    <span style="color:{accent}; margin-right:5px">{icon}</span>{label}
                </div>
                <div style="font-size:22px; font-weight:700; color:#0D1B17;
                            letter-spacing:-0.4px; white-space:nowrap;
                            overflow:hidden; text-overflow:ellipsis">
                    {value}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Aba: Pagamentos Concluídos
# ══════════════════════════════════════════════════════════════════════════════

def _render_pagamentos_tab() -> None:
    # ── Carregar pagamentos ───────────────────────────────────────────────────
    df_pag = load_payments()

    if df_pag is None or df_pag.empty:
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;
                        justify-content:center;min-height:50vh;text-align:center;gap:14px">
                <div style="font-size:52px;opacity:0.18">✅</div>
                <p style="font-size:20px;font-weight:600;
                          color:{COLORS['text_primary']};margin:0">
                    Nenhum pagamento concluído ainda
                </p>
                <p style="font-size:13px;color:{COLORS['text_subtle']};
                          margin:0;max-width:420px;line-height:1.7">
                    Quando uma cobrança for marcada como
                    <strong style="color:{COLORS['text_primary']}">Pago</strong> na aba
                    <strong style="color:{COLORS['text_primary']}">Histórico de Cobranças</strong>,
                    ela aparecerá automaticamente aqui.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    df_pag = df_pag.reset_index(drop=True)

    # ── Preparar colunas visíveis ─────────────────────────────────────────────
    cols_avail = [c for c in _PAG_ORDERED_COLS if c in df_pag.columns]
    df_view = df_pag[cols_avail].copy()
    df_view.rename(columns=HISTORY_LABELS, inplace=True)

    cod_label  = HISTORY_LABELS.get("COD_LANCAMENTO",  "Código")
    venc_label = HISTORY_LABELS.get("DATA_VENCIMENTO", "Data Vencimento")
    pag_label  = HISTORY_LABELS.get("DATA_PAGAMENTO",  "Data Pagamento")
    sup_label  = HISTORY_LABELS.get(COLS["supplier"],  "Fornecedor")
    cnpj_label = HISTORY_LABELS.get("CNPJ_FORNECEDOR", "CNPJ")
    val_label  = HISTORY_LABELS.get(COLS["value_brl"], "Valor (R$)")
    min_label  = HISTORY_LABELS.get(COLS["minutes"],   "Min. Gerados")
    qty_label  = HISTORY_LABELS.get(COLS["quantity"],  "Qtd")
    ord_label  = HISTORY_LABELS.get(COLS["order"],     "OM")

    for col in (val_label, min_label, qty_label):
        if col in df_view.columns:
            df_view[col] = pd.to_numeric(df_view[col], errors="coerce")

    # ── Situação do pagamento: fato permanente (não muda com o tempo), por
    # isso é calculado aqui a partir das duas datas persistidas, e não
    # precisa ser recalculado "ao vivo" como o Dias-para-Vencer do Histórico ─
    situ_label = "Situação"
    if venc_label in df_view.columns and pag_label in df_view.columns:
        def _situacao(row):
            dias, atrasado = payment_punctuality(row[pag_label], row[venc_label])
            if atrasado is None:
                return "—"
            if atrasado:
                return f"Atraso de {dias}d"
            return "No prazo"
        df_view[situ_label] = df_view.apply(_situacao, axis=1)

    # ── Pesquisa por Fornecedor ou CNPJ ────────────────────────────────────────
    opcoes_busca = ["Todos os Fornecedores"]
    if sup_label in df_view.columns and cnpj_label in df_view.columns:
        pares = (
            df_view[[sup_label, cnpj_label]]
            .drop_duplicates()
            .sort_values(sup_label)
        )
        opcoes_busca += [f"{r[sup_label]} — {r[cnpj_label]}" for _, r in pares.iterrows()]

    col_busca, col_clear = st.columns([3, 1])
    with col_busca:
        busca_sel = st.selectbox(
            "Pesquisar por Fornecedor ou CNPJ",
            options=opcoes_busca,
            key="pag_busca_fornecedor",
            help="Selecione um fornecedor (ou seu CNPJ) para filtrar os pagamentos.",
        )
    with col_clear:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        if st.button("↺ Limpar Pesquisa", key="pag_clear", use_container_width=True):
            st.session_state.pop("pag_busca_fornecedor", None)
            st.rerun()

    df_filtered = df_view.copy()
    if busca_sel != "Todos os Fornecedores":
        fornecedor_sel = busca_sel.split(" — ")[0]
        df_filtered = df_filtered[df_filtered[sup_label] == fornecedor_sel]

    # ── KPIs (refletem a pesquisa aplicada) ──────────────────────────────────
    total_value    = df_filtered[val_label].sum() if val_label in df_filtered.columns else 0.0
    n_lancamentos  = df_filtered[cod_label].nunique() if cod_label in df_filtered.columns else 0
    n_fornecedores = df_filtered[sup_label].nunique() if sup_label in df_filtered.columns else 0

    n_no_prazo = n_atraso = 0
    if situ_label in df_filtered.columns and cod_label in df_filtered.columns:
        _unicos = df_filtered.drop_duplicates(subset=[cod_label])
        n_no_prazo = int((_unicos[situ_label] == "No prazo").sum())
        n_atraso   = int(_unicos[situ_label].astype(str).str.startswith("Atraso").sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    _metric_kpi_card(c1, "💰", "VALOR TOTAL PAGO",   f"R$ {total_value:,.2f}", "#1D9E75")
    _metric_kpi_card(c2, "🧾", "LANÇAMENTOS PAGOS",  str(n_lancamentos),       "#534AB7")
    _metric_kpi_card(c3, "🏢", "FORNECEDORES",       str(n_fornecedores),      "#0F86A3")
    _metric_kpi_card(c4, "✅", "PAGOS NO PRAZO",     str(n_no_prazo),          "#00B884")
    _metric_kpi_card(c5, "⚠️", "PAGOS COM ATRASO",   str(n_atraso),            "#D85A30")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Badge de pesquisa ativa
    st.markdown(
        f"""
        <div style="
            font-size:11px; color:{COLORS['text_subtle']};
            background:rgba(0,229,160,0.08);
            border:1px solid rgba(0,229,160,0.18);
            border-radius:6px; padding:6px 14px; margin-bottom:12px;
            display:inline-block;
        ">
            🔎 {busca_sel} &nbsp;·&nbsp; {len(df_filtered)} item(ns)
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabela customizada HTML/CSS ───────────────────────────────────────────
    display_df = df_filtered.copy()

    if val_label in display_df.columns:
        display_df[val_label] = display_df[val_label].apply(lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else "")
    if min_label in display_df.columns:
        display_df[min_label] = display_df[min_label].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")
    if qty_label in display_df.columns:
        display_df[qty_label] = display_df[qty_label].apply(lambda v: f"{int(float(v)):,}" if pd.notna(v) else "")
    if ord_label in display_df.columns:
        display_df[ord_label] = display_df[ord_label].apply(lambda v: f"{int(float(v))}" if pd.notna(v) else "")
    if "Real Cortado" in display_df.columns:
        display_df["Real Cortado"] = display_df["Real Cortado"].apply(lambda v: f"{int(float(v)):,}" if pd.notna(v) else "")

    if situ_label in display_df.columns:
        def _situ_badge(s):
            if s == "No prazo":
                return '<span class="badge-status status-pago">✅ No prazo</span>'
            if isinstance(s, str) and s.startswith("Atraso"):
                return f'<span class="badge-status status-contestado">⚠️ {s}</span>'
            return '<span style="color:#9A6B1E">—</span>'
        display_df[situ_label] = display_df[situ_label].apply(_situ_badge)

    headers = list(display_df.columns)

    TH = (
        "padding:11px 14px;text-align:center;color:#FFFFFF;font-weight:600;"
        "font-size:10px;text-transform:uppercase;letter-spacing:0.9px;"
        "background:#00805C;border-bottom:2px solid #00B884;"
        "white-space:nowrap;position:sticky;top:0;z-index:1;"
    )
    TH_L = TH + "text-align:left;"

    head_html = "".join(
        f'<th style="{TH_L if h in ("Fornecedor", "Remonte") else TH}">✦ {h}</th>'
        for h in headers
    )

    def _make_cell(h, val, row_bg):
        is_left = h in ("Fornecedor", "Remonte")
        align = "text-align:left;" if is_left else "text-align:center;"
        base_td = (
            f"padding:9px 14px;font-size:12.5px;color:#0D1B17;"
            f"border-bottom:1px solid rgba(0,229,160,0.12);"
            f"{align}{row_bg}"
        )
        return f'<td style="{base_td}">{val}</td>'

    rows_html = "".join(
        f"<tr>" + "".join(
            _make_cell(h, row[h], "background:#FFFFFF;" if i % 2 == 1 else "background:#F2F7F5;")
            for h in headers
        ) + "</tr>"
        for i, (_, row) in enumerate(display_df.iterrows())
    )

    table_html = f"""
    <style>
      .nv-pag-table-wrap {{ scrollbar-width: thin; }}
      .nv-pag-table-wrap::-webkit-scrollbar {{ width:6px; height:6px; }}
      .nv-pag-table-wrap::-webkit-scrollbar-track {{ background:#FFFFFF; border-radius:3px; }}
      .nv-pag-table-wrap::-webkit-scrollbar-thumb {{ background:rgba(0,229,160,0.45); border-radius:3px; }}
      .nv-pag-table-wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(0,229,160,0.70); }}
      .nv-pag-table-wrap tr:hover td {{ background:rgba(0,229,160,0.14)!important; transition:background 0.15s; }}
      .badge-status {{
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        display: inline-block;
      }}
      .status-pago {{ background: #00E5A0 !important; color: #FFFFFF !important; }}
      .status-contestado {{ background: #D85A30 !important; color: #FFFFFF !important; }}
    </style>
    <div class="nv-pag-table-wrap" style="
        max-height:480px; overflow:auto; border-radius:12px;
        border:1px solid rgba(0,229,160,0.32);
        border-top:2px solid #00B884;
        background:#F2F7F5;
        box-shadow:0 0 22px rgba(0,229,160,0.10);
    ">
      <table style="width:100%;border-collapse:collapse;min-width:1100px;">
        <thead><tr>{head_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Botão de exportar Excel executivo ─────────────────────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    btn_dl, _sp = st.columns([1, 3])
    with btn_dl:
        _xlsx_bytes = generate_payments_xlsx_bytes() if df_pag is not None and not df_pag.empty else None
        if _xlsx_bytes:
            st.download_button(
                label="📊  Baixar Excel Executivo",
                data=_xlsx_bytes,
                file_name=f"pagamentos_concluidos_{date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_pagamentos_excel",
                use_container_width=True,
                help="Baixa o relatório executivo completo (todos os pagamentos, "
                     "independente da pesquisa acima).",
            )
        else:
            st.button("📊  Baixar Excel Executivo", disabled=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# Aba: Devolução
# ══════════════════════════════════════════════════════════════════════════════

# Mesma estrutura de colunas da aba Pagamentos (sem "Status" — aqui o status é
# sempre "Devolução", implícito pela aba).
_DEV_ORDERED_COLS = _PAG_ORDERED_COLS


def _render_devolucao_tab() -> None:
    # ── Carregar devoluções ───────────────────────────────────────────────────
    df_dev = load_devolucoes()

    if df_dev is None or df_dev.empty:
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;
                        justify-content:center;min-height:50vh;text-align:center;gap:14px">
                <div style="font-size:52px;opacity:0.18">🔄</div>
                <p style="font-size:20px;font-weight:600;
                          color:{COLORS['text_primary']};margin:0">
                    Nenhuma devolução registrada ainda
                </p>
                <p style="font-size:13px;color:{COLORS['text_subtle']};
                          margin:0;max-width:420px;line-height:1.7">
                    Quando uma cobrança for marcada como
                    <strong style="color:{COLORS['text_primary']}">Devolução</strong> na aba
                    <strong style="color:{COLORS['text_primary']}">Histórico de Cobranças</strong>
                    — ou seja, quando a oficina fornecedora optar por consertar as peças
                    com defeito em vez de pagar o desconto — ela aparecerá aqui.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    df_dev = df_dev.reset_index(drop=True)

    # ── Preparar colunas visíveis ─────────────────────────────────────────────
    cols_avail = [c for c in _DEV_ORDERED_COLS if c in df_dev.columns]
    df_view = df_dev[cols_avail].copy()
    df_view.rename(columns=HISTORY_LABELS, inplace=True)

    cod_label  = HISTORY_LABELS.get("COD_LANCAMENTO",  "Código")
    sup_label  = HISTORY_LABELS.get(COLS["supplier"],  "Fornecedor")
    cnpj_label = HISTORY_LABELS.get("CNPJ_FORNECEDOR", "CNPJ")
    val_label  = HISTORY_LABELS.get(COLS["value_brl"], "Valor (R$)")
    min_label  = HISTORY_LABELS.get(COLS["minutes"],   "Min. Gerados")
    qty_label  = HISTORY_LABELS.get(COLS["quantity"],  "Qtd")
    ord_label  = HISTORY_LABELS.get(COLS["order"],     "OM")

    for col in (val_label, min_label, qty_label):
        if col in df_view.columns:
            df_view[col] = pd.to_numeric(df_view[col], errors="coerce")

    # ── Pesquisa por Fornecedor ou CNPJ ────────────────────────────────────────
    opcoes_busca = ["Todos os Fornecedores"]
    if sup_label in df_view.columns and cnpj_label in df_view.columns:
        pares = (
            df_view[[sup_label, cnpj_label]]
            .drop_duplicates()
            .sort_values(sup_label)
        )
        opcoes_busca += [f"{r[sup_label]} — {r[cnpj_label]}" for _, r in pares.iterrows()]

    col_busca, col_clear = st.columns([3, 1])
    with col_busca:
        busca_sel = st.selectbox(
            "Pesquisar por Fornecedor ou CNPJ",
            options=opcoes_busca,
            key="dev_busca_fornecedor",
            help="Selecione um fornecedor (ou seu CNPJ) para filtrar as devoluções.",
        )
    with col_clear:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        if st.button("↺ Limpar Pesquisa", key="dev_clear", use_container_width=True):
            st.session_state.pop("dev_busca_fornecedor", None)
            st.rerun()

    df_filtered = df_view.copy()
    if busca_sel != "Todos os Fornecedores":
        fornecedor_sel = busca_sel.split(" — ")[0]
        df_filtered = df_filtered[df_filtered[sup_label] == fornecedor_sel]

    # ── KPIs (refletem a pesquisa aplicada) ──────────────────────────────────
    total_value    = df_filtered[val_label].sum() if val_label in df_filtered.columns else 0.0
    total_minutes  = df_filtered[min_label].sum() if min_label in df_filtered.columns else 0.0
    total_pieces   = int(df_filtered[qty_label].sum()) if qty_label in df_filtered.columns else 0
    n_lancamentos  = df_filtered[cod_label].nunique() if cod_label in df_filtered.columns else 0
    n_fornecedores = df_filtered[sup_label].nunique() if sup_label in df_filtered.columns else 0
    n_orders       = df_filtered[ord_label].nunique() if ord_label in df_filtered.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    _metric_kpi_card(c1, "💰", "VALOR TOTAL DEVOLVIDO",  f"R$ {total_value:,.2f}", "#0F86A3")
    _metric_kpi_card(c2, "🧾", "LANÇAMENTOS DEVOLVIDOS",  str(n_lancamentos),       "#534AB7")
    _metric_kpi_card(c3, "🏢", "FORNECEDORES",            str(n_fornecedores),      "#00B884")
    _metric_kpi_card(c4, "🧵", "PEÇAS DEVOLVIDAS",        f"{total_pieces:,}",      "#D85A30")
    _metric_kpi_card(c5, "📦", "ORDENS ÚNICAS (OM)",      str(n_orders),            "#EF9F27")

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # Badge de pesquisa ativa
    st.markdown(
        f"""
        <div style="
            font-size:11px; color:{COLORS['text_subtle']};
            background:rgba(0,229,160,0.08);
            border:1px solid rgba(0,229,160,0.18);
            border-radius:6px; padding:6px 14px; margin-bottom:12px;
            display:inline-block;
        ">
            🔎 {busca_sel} &nbsp;·&nbsp; {len(df_filtered)} item(ns)
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabela (reaproveita o mesmo componente HTML/CSS da aba Histórico) ────
    display_df = df_filtered.copy()

    if val_label in display_df.columns:
        display_df[val_label] = display_df[val_label].apply(lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else "")
    if min_label in display_df.columns:
        display_df[min_label] = display_df[min_label].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")
    if qty_label in display_df.columns:
        display_df[qty_label] = display_df[qty_label].apply(lambda v: f"{int(float(v)):,}" if pd.notna(v) else "")
    if ord_label in display_df.columns:
        display_df[ord_label] = display_df[ord_label].apply(lambda v: f"{int(float(v))}" if pd.notna(v) else "")
    if "Real Cortado" in display_df.columns:
        display_df["Real Cortado"] = display_df["Real Cortado"].apply(lambda v: f"{int(float(v)):,}" if pd.notna(v) else "")

    if display_df.empty:
        st.info("Nenhuma devolução encontrada para a pesquisa atual.")
    else:
        _render_simple_table(display_df, left_cols=frozenset({sup_label, "Remonte"}), height=440)

    # ── Botões de exportação (Excel + Prévia/Imprimir PDF) ────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    btn_dl, btn_pdf, _sp = st.columns([1, 1, 2])

    with btn_dl:
        _xlsx_bytes = generate_devolucoes_xlsx_bytes() if df_dev is not None and not df_dev.empty else None
        if _xlsx_bytes:
            st.download_button(
                label="📊  Baixar Excel Executivo",
                data=_xlsx_bytes,
                file_name=f"devolucoes_{date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_devolucoes_excel",
                use_container_width=True,
                help="Baixa o relatório executivo completo (todas as devoluções, "
                     "independente da pesquisa acima).",
            )
        else:
            st.button("📊  Baixar Excel Executivo", disabled=True, use_container_width=True)

    with btn_pdf:
        if len(df_filtered) > 0:
            totals_dev = dict(
                n_records=len(df_filtered),
                total_minutes=total_minutes,
                total_value=total_value,
                total_pieces=total_pieces,
                n_orders=n_orders,
                n_cobrancas=n_lancamentos,
            )
            html_dev = _generate_historico_html(
                df_filtered, totals_dev, f"Pesquisa: {busca_sel}",
                titulo="🔄 Devolução de Peças", badge="devolucoes",
            )
            _render_print_button(html_dev)
        else:
            st.button(
                "🖨️  Prévia / Imprimir PDF", disabled=True,
                use_container_width=True,
                help="Nenhum registro para exportar.",
            )


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

@page_guard
def main() -> None:
    require_login()
    render_user_sidebar()

    # ── Migra cobranças já pagas (lançadas antes da página Pagamentos
    # Concluídos existir) para pagamentos_concluidos. Idempotente — não faz
    # nada se já estiver tudo migrado. Fica dentro do main() (após o login e
    # sob o page_guard) para que uma falha de banco vire mensagem amigável,
    # em vez de quebrar a página ainda no import do módulo.
    migrate_paid_to_payments()
    # ── Compatibilidade: converte lançamentos com o status legado "Contestado"
    # (opção removida em favor de "Devolução") para devolucoes. Idempotente.
    migrate_contestado_to_devolucao()

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;
                    border-bottom:1px solid rgba(0,0,0,0.06);
                    margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">
                    🗃️ Gestão de Cobranças
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_hist, tab_cobranca, tab_pag, tab_dev = st.tabs([
        "🗃️ Histórico de Cobranças",
        "💰 Cobrança de Fornecedores",
        "✅ Pagamentos Concluídos",
        "🔄 Devolução",
    ])

    with tab_hist:
        _render_historico_tab()

    with tab_cobranca:
        _render_cobranca_tab()

    with tab_pag:
        _render_pagamentos_tab()

    with tab_dev:
        _render_devolucao_tab()

    # ── Status sidebar (comum às 4 abas) ──────────────────────────────────────
    st.sidebar.markdown(
        '<hr style="border-color:rgba(0,0,0,0.06);margin:16px 0">',
        unsafe_allow_html=True,
    )
   
   # st.sidebar.markdown(
   #     '<div style="font-size:10.5px;color:#00E5A0;padding:6px 8px;'
   #     'border-radius:6px;background:rgba(0,229,160,0.06);'
   #     'border:1px solid #00E5A033;">✓ Banco Postgres (Supabase) conectado</div>',
   #     unsafe_allow_html=True,
   # )


main()
