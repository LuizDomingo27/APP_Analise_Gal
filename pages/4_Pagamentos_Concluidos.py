# -*- coding: utf-8 -*-
"""
Página: Pagamentos Concluídos — bd_pagamentos.xlsx

Todas as cobranças já pagas. Cada lançamento (que pode ter vários itens —
um por defeito/OM) tem um Código de Pagamento único, o que permite
distinguir várias contas pagas do mesmo fornecedor/CNPJ.

Recursos:
  - Selectbox de pesquisa por Fornecedor ou CNPJ (sidebar)
  - Código do Pagamento único por lançamento
  - Tabela detalhada com Situação (pago no prazo / com atraso)
  - Botão para baixar o Excel executivo (bd_pagamentos.xlsx)
"""

from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Pagamentos Concluídos",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config.settings import COLS, COLORS
from src.data.cobranca_history import HISTORY_LABELS, payment_punctuality
from src.data.payment_history import BD_PAGAMENTOS, load_payments

# ── CSS global — mesma identidade visual das outras páginas ─────────────────
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
    hr { border-color: rgba(0,0,0,0.06) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Ordem das colunas na tabela (sem "Status" — aqui é sempre "Pago") ───────
_ORDERED_COLS = [
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


def _kpi_card(col, icon: str, label: str, value: str, accent: str) -> None:
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


def main() -> None:
    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;
                    border-bottom:1px solid rgba(0,0,0,0.06);
                    margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">
                    ✅ Pagamentos Concluídos
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(0,229,160,0.18);
                             padding:3px 10px;border-radius:20px;
                             border:1px solid rgba(0,229,160,0.3)">
                    bd_pagamentos.xlsx
                </span>
            </div>
            <p style="color:{COLORS['text_muted']};font-size:13px;margin:5px 0 0">
                Todas as cobranças já pagas. Cada lançamento tem um
                <strong>Código de Pagamento</strong> único — útil quando o mesmo
                fornecedor/CNPJ tem várias contas pagas.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
    cols_avail = [c for c in _ORDERED_COLS if c in df_pag.columns]
    df_view = df_pag[cols_avail].copy()
    df_view.rename(columns=HISTORY_LABELS, inplace=True)

    cod_label  = HISTORY_LABELS.get("COD_LANCAMENTO",  "Código")
    dte_label  = HISTORY_LABELS.get("DATA_COBRANCA",   "Data Cobrança")
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

    # ── 1. Selectbox de pesquisa por Fornecedor ou CNPJ (sidebar) ────────────
    st.sidebar.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:#4A5752;margin-bottom:12px">Pesquisar</p>',
        unsafe_allow_html=True,
    )

    opcoes_busca = ["Todos os Fornecedores"]
    if sup_label in df_view.columns and cnpj_label in df_view.columns:
        pares = (
            df_view[[sup_label, cnpj_label]]
            .drop_duplicates()
            .sort_values(sup_label)
        )
        opcoes_busca += [f"{r[sup_label]} — {r[cnpj_label]}" for _, r in pares.iterrows()]

    busca_sel = st.sidebar.selectbox(
        "Fornecedor ou CNPJ",
        options=opcoes_busca,
        key="pag_busca_fornecedor",
        label_visibility="collapsed",
        help="Selecione um fornecedor (ou seu CNPJ) para filtrar os pagamentos.",
    )

    df_filtered = df_view.copy()
    if busca_sel != "Todos os Fornecedores":
        fornecedor_sel = busca_sel.split(" — ")[0]
        df_filtered = df_filtered[df_filtered[sup_label] == fornecedor_sel]

    if st.sidebar.button("↺ Limpar Pesquisa", key="pag_clear", use_container_width=True):
        st.session_state.pop("pag_busca_fornecedor", None)
        st.rerun()

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
    _kpi_card(c1, "💰", "VALOR TOTAL PAGO",   f"R$ {total_value:,.2f}", "#1D9E75")
    _kpi_card(c2, "🧾", "LANÇAMENTOS PAGOS",  str(n_lancamentos),       "#534AB7")
    _kpi_card(c3, "🏢", "FORNECEDORES",       str(n_fornecedores),      "#0F86A3")
    _kpi_card(c4, "✅", "PAGOS NO PRAZO",     str(n_no_prazo),          "#00B884")
    _kpi_card(c5, "⚠️", "PAGOS COM ATRASO",   str(n_atraso),            "#D85A30")

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

    # ── 3. Tabela customizada HTML/CSS ───────────────────────────────────────
    display_df = df_filtered.copy()

    if val_label in display_df.columns:
        display_df[val_label] = display_df[val_label].apply(lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else "")
    if min_label in display_df.columns:
        display_df[min_label] = display_df[min_label].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")
    if qty_label in display_df.columns:
        display_df[qty_label] = display_df[qty_label].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "")
    if ord_label in display_df.columns:
        display_df[ord_label] = display_df[ord_label].apply(lambda v: f"{int(v)}" if pd.notna(v) else "")
    if "Real Cortado" in display_df.columns:
        display_df["Real Cortado"] = display_df["Real Cortado"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "")

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

    # ── 4. Botão de exportar Excel executivo ──────────────────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    btn_dl, _sp = st.columns([1, 3])
    with btn_dl:
        if BD_PAGAMENTOS.exists():
            with open(BD_PAGAMENTOS, "rb") as f:
                st.download_button(
                    label="📊  Baixar Excel Executivo",
                    data=f.read(),
                    file_name=f"pagamentos_concluidos_{date.today().isoformat()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_pagamentos_excel",
                    use_container_width=True,
                    help="Baixa o relatório executivo completo (todos os pagamentos, "
                         "independente da pesquisa acima).",
                )
        else:
            st.button("📊  Baixar Excel Executivo", disabled=True, use_container_width=True)

    # ── Status sidebar ────────────────────────────────────────────────────────
    st.sidebar.markdown(
        '<hr style="border-color:rgba(0,0,0,0.06);margin:16px 0">',
        unsafe_allow_html=True,
    )
    ok_color = "#00E5A0" if BD_PAGAMENTOS.exists() else "#EF9F27"
    ok_txt   = "bd_pagamentos.xlsx presente" if BD_PAGAMENTOS.exists() else "Arquivo ainda não criado"
    st.sidebar.markdown(
        f'<div style="font-size:10.5px;color:{ok_color};padding:6px 8px;'
        f'border-radius:6px;background:rgba(0,229,160,0.06);'
        f'border:1px solid {ok_color}33;">✓ {ok_txt}</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        f'<div style="font-size:10px;color:#00805C;margin-top:8px;padding:4px 8px">'
        f'{len(df_pag)} item(ns) pago(s) no total</div>',
        unsafe_allow_html=True,
    )


main()
