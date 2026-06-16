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
    BD_COBRANCA,
    HISTORY_LABELS,
    STATUS_OPTIONS,
    load_history,
    update_status,
)
import base64
import streamlit.components.v1 as components
from src.ui.preview import _generate_historico_html
# Force reload comment

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
    "DATA_COBRANCA",
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

# Ícone e cor de fundo (HTML) por status
_STATUS_BADGE = {
    "Pago":       ("✅", "#00E5A0", "#FFFFFF"),
    "Pendente":   ("⏳", "#EF9F27", "#E8EFEC"),
    "Contestado": ("⚠️", "#D85A30", "#FFFFFF"),
}


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
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
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
                Registro acumulado de todas as cobranças confirmadas.
                Edite o status diretamente na tabela e clique em <strong>Salvar alterações</strong>.
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
    cnpj_label   = HISTORY_LABELS.get("CNPJ_FORNECEDOR", "CNPJ")

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
        '<p style="font-size:11px;color:#4A5752;margin:12px 0 4px">Fornecedor ou CNPJ:</p>',
        unsafe_allow_html=True,
    )
    search_term = st.sidebar.text_input(
        "Buscar", placeholder="Digite nome ou CNPJ…",
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
            for col in (sup_label, cnpj_label)
            if col in df_filtered.columns
        ]
        if masks:
            combined = masks[0]
            for m in masks[1:]:
                combined = combined | m
            df_filtered = df_filtered[combined]
        filters_parts.append(f"Busca: \"{search_term.strip()}\"")
    else:
        filters_parts.append("Fornecedor/CNPJ: todos")

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
    n_records     = len(df_filtered)

    totals = dict(
        n_records=n_records,
        total_minutes=total_minutes,
        total_value=total_value,
        total_pieces=total_pieces,
        n_orders=n_orders,
    )

    # ── 5 Cards KPI ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    _kpi_card(c1, "🧵", "PEÇAS COM DEFEITO",    f"{total_pieces:,}",         "#0F86A3")
    _kpi_card(c2, "📋", "TOTAL DEFEITOS",        str(n_records),              "#00B884")
    _kpi_card(c3, "⏱️", "TOTAL MINUTOS",         f"{total_minutes:,.0f} min", "#00E5A0")
    _kpi_card(c4, "💰", "VALOR TOTAL",           f"R$ {total_value:,.2f}",    "#E24B4A")
    _kpi_card(c5, "📦", "ORDENS ÚNICAS (OM)",    str(n_orders),               "#EF9F27")

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

    # ── Tabela Customizada HTML/CSS ───────────────────────────────────────────
    display_df = df_filtered.copy()
    
    # Formatação dos dados para exibição na tabela HTML
    display_df[val_label] = display_df[val_label].apply(lambda v: f"R$ {float(v):,.2f}" if pd.notna(v) else "")
    display_df[min_label] = display_df[min_label].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")
    display_df[qty_label] = display_df[qty_label].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "")
    display_df[ord_label] = display_df[ord_label].apply(lambda v: f"{int(v)}" if pd.notna(v) else "")
    if "Real Cortado" in display_df.columns:
        display_df["Real Cortado"] = display_df["Real Cortado"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "")

    if status_label in display_df.columns:
        display_df[status_label] = display_df[status_label].apply(lambda s: 
            '<span class="badge-status status-pago">✅ Pago</span>' if str(s).strip() == "Pago"
            else ('<span class="badge-status status-contestado">⚠️ Contestado</span>' if str(s).strip() == "Contestado"
            else '<span class="badge-status status-pendente">⏳ Pendente</span>')
        )

    # Remover _orig_idx da exibição
    orig_idx_col = "_orig_idx"
    table_view_df = display_df.drop(columns=[orig_idx_col], errors="ignore")

    # Renderizar tabela customizada
    headers = list(table_view_df.columns)
    
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
        f"<tr>" + "".join(_make_cell(h, row[h], "background:#FFFFFF;" if i % 2 == 1 else "background:#F2F7F5;") for h in headers) + "</tr>"
        for i, (_, row) in enumerate(table_view_df.iterrows())
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

    # ── Painel de Controle de Status ──────────────────────────────────────────
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    with st.expander("📝 Atualizar Status de Lançamento", expanded=True):
        col_rec, col_st, col_act = st.columns([2, 1, 1])
        charge_opts = []
        for idx, row in df_filtered.iterrows():
            opt_label = f"{row[sup_label]} | OM: {int(row[ord_label])} | R$ {float(row[val_label]):,.2f} ({row[dte_label]})"
            charge_opts.append((opt_label, row[orig_idx_col], row[status_label]))
        
        if charge_opts:
            selected_opt = col_rec.selectbox(
                "Selecionar Registro de Cobrança",
                options=charge_opts,
                format_func=lambda x: f"[{x[2]}] {x[0]}",
                key="select_charge_to_update"
            )
            
            curr_st = selected_opt[2]
            status_idx = STATUS_OPTIONS.index(curr_st) if curr_st in STATUS_OPTIONS else 0
            
            new_st = col_st.selectbox(
                "Alterar Status para",
                options=STATUS_OPTIONS,
                index=status_idx,
                key="new_status_select"
            )
            
            if col_act.button("💾 Salvar Alteração", use_container_width=True, key="btn_update_status_db"):
                ok = update_status(selected_opt[1], new_st)
                if ok:
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
        if BD_COBRANCA.exists():
            with open(BD_COBRANCA, "rb") as f:
                st.download_button(
                    label="⬇️  Baixar Excel",
                    data=f.read(),
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
            html_hist_b64 = base64.b64encode(html_hist.encode("utf-8")).decode()
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
  const _HTML_B64 = "{html_hist_b64}";
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
    ok_color = "#00E5A0" if BD_COBRANCA.exists() else "#EF9F27"
    ok_txt   = "bd_cobranca.xlsx presente" if BD_COBRANCA.exists() else "Arquivo ainda não criado"
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
