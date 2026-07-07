# -*- coding: utf-8 -*-
"""
Pagina: Historico de Cobracas — bd_cobranca.xlsx
Registro acumulado de todas as cobracas confirmadas.

Recursos:
  - 5 cards KPI: total pecas com defeito, defeitos (linhas), minutos, valor, ordens unicas
  - Filtros por intervalo de datas, fornecedor / CNPJ e STATUS
  - Tabela interativa editável (coluna Status inline)
  - Botão "Salvar alterações de status" com confirmação
  - Botao Baixar Excel
  - Botao Imprimir PDF (reportlab: tabela + KPIs de resumo)

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
    generate_history_xlsx_bytes,
    generate_single_charge_xlsx_bytes,
    group_charges,
    status_badge_html,
    situacao_badge_html,
)
import base64
import streamlit.components.v1 as components
from src.ui.preview import _generate_historico_html
from src.auth.session import require_login, render_user_sidebar
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
    [data-testid="stDownloadButton"] > button {
        height: 38px !important;
        min-width: 160px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 0 20px !important;
    }
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    hr { border-color: rgba(0,0,0,0.06) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Ordem das colunas na tabela ───────────────────────────────────────────────
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


# ══════════════════════════════════════════════════════════════════════════════
# Card KPI
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
# Tabela de extrato (resumo por lançamento) + popup de detalhes
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

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;
                    border-bottom:1px solid rgba(0,0,0,0.06);
                    margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">
                    🗃️ Histórico de Cobranças
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(0,229,160,0.18);
                             padding:3px 10px;border-radius:20px;
                             border:1px solid rgba(0,229,160,0.3)">
                    bd_cobranca.xlsx
                </span>
            </div>
            <p style="color:{COLORS['text_muted']};font-size:13px;margin:5px 0 0">
                Registro acumulado de todas as cobranças confirmadas, exceto as já pagas
                — essas ficam na aba <strong>Pagamentos Concluídos</strong>.
                Edite o status diretamente no painel abaixo.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
                    a primeira cobrança na página
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

    # ── Filtros (sidebar) ─────────────────────────────────────────────────────
    st.sidebar.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:#4A5752;margin-bottom:12px">Filtros</p>',
        unsafe_allow_html=True,
    )

    # Filtro de data
    date_from = date_to = None
    if dte_label in df_view.columns:
        try:
            dates_parsed = pd.to_datetime(df_view[dte_label], format="%d/%m/%Y", errors="coerce")
            min_date = dates_parsed.dropna().min().date()
            max_date = dates_parsed.dropna().max().date()
        except Exception:
            min_date = date.today() - timedelta(days=365)
            max_date = date.today()

        st.sidebar.markdown(
            '<p style="font-size:11px;color:#4A5752;margin:0 0 4px">Período:</p>',
            unsafe_allow_html=True,
        )
        date_from = st.sidebar.date_input(
            "De", value=min_date, min_value=min_date, max_value=max_date,
            key="hist_date_from", label_visibility="collapsed",
        )
        date_to = st.sidebar.date_input(
            "Até", value=max_date, min_value=min_date, max_value=max_date,
            key="hist_date_to", label_visibility="collapsed",
        )

    st.sidebar.markdown(
        '<p style="font-size:11px;color:#4A5752;margin:12px 0 4px">Fornecedor, CNPJ ou Código:</p>',
        unsafe_allow_html=True,
    )
    search_term = st.sidebar.text_input(
        "Buscar", placeholder="Digite nome, CNPJ ou código…",
        key="hist_search", label_visibility="collapsed",
    )

    # ── Filtro por status ─────────────────────────────────────────────────────
    st.sidebar.markdown(
        '<p style="font-size:11px;color:#4A5752;margin:12px 0 4px">Status:</p>',
        unsafe_allow_html=True,
    )
    status_filter = st.sidebar.multiselect(
        "Status",
        options=STATUS_OPTIONS,
        default=STATUS_OPTIONS,
        key="hist_status_filter",
        label_visibility="collapsed",
    )

    if st.sidebar.button("↺ Limpar Filtros", key="hist_clear", use_container_width=True):
        for k in ("hist_date_from", "hist_date_to", "hist_search", "hist_status_filter"):
            st.session_state.pop(k, None)
        st.rerun()

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

    # ── Legenda de status ─────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap">
            <span style="font-size:11px;padding:3px 10px;border-radius:10px;
                         background:#00E5A0;color:#fff;font-weight:600">
                ✅ Pago
            </span>
            <span style="font-size:11px;padding:3px 10px;border-radius:10px;
                         background:#EF9F27;color:#0D1B17;font-weight:600">
                ⏳ Pendente
            </span>
            <span style="font-size:11px;padding:3px 10px;border-radius:10px;
                         background:#D85A30;color:#fff;font-weight:600">
                ⚠️ Contestado
            </span>
            <span style="font-size:11px;color:#4A5752;align-self:center">
                &nbsp;· Selecione o status na coluna e clique em Salvar alterações
            </span>
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
        st.caption(
            "Uma cobrança pode ter vários itens (um por defeito/OM) — todos compartilham "
            "o mesmo Código. A alteração abaixo sempre vale para o lançamento inteiro. "
            "Ao marcar como **Pago**, a cobrança sai deste histórico e passa para a aba "
            "**Pagamentos Concluídos**."
        )
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
                key="new_status_select"
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
                    )
                else:
                    st.markdown(
                        f"<div style='margin-top:1.8rem;font-size:11px;color:{COLORS.get('text_subtle', '#7C8985')}'>"
                        "Disponível ao marcar como Pago</div>",
                        unsafe_allow_html=True,
                    )
            
            if col_act.button("💾 Salvar Alteração", use_container_width=True, key="btn_update_status_db"):
                cod_sel = selected_opt[1]
                ok = update_lancamento_status(cod_sel, new_st, data_pagamento=data_pagamento_input)
                if ok:
                    if new_st == "Pago":
                        st.success(
                            f"✅ Cobrança paga com sucesso! Código **{cod_sel}** — "
                            "consulte os detalhes na aba **Pagamentos Concluídos**."
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

    # ── Status sidebar ────────────────────────────────────────────────────────
    st.sidebar.markdown(
        '<hr style="border-color:rgba(0,0,0,0.06);margin:16px 0">',
        unsafe_allow_html=True,
    )
    ok_color = "#00E5A0"
    ok_txt   = "Banco Postgres (Supabase) conectado"
    st.sidebar.markdown(
        f'<div style="font-size:10.5px;color:{ok_color};padding:6px 8px;'
        f'border-radius:6px;background:rgba(0,229,160,0.06);'
        f'border:1px solid {ok_color}33;">✓ {ok_txt}</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        f'<div style="font-size:10px;color:#00805C;margin-top:8px;padding:4px 8px">'
        f'{len(df_hist) - 1} registro(s) no total</div>',
        unsafe_allow_html=True,
    )


main()
