"""
Análise de Defeitos de Produção — Streamlit App
Entry point: page config, CSS injection, top-level orchestration.

Carregamento de dados (novo fluxo):
  • Startup normal   → lê bd_principal.xlsx direto da pasta dataset/
  • Primeira vez     → exibe uploader para criar a base (comportamento legado)
  • Importar novos   → expander discreto na sidebar faz append diário
"""

import streamlit as st
from src.config.settings import PAGE_CONFIG, COLORS
from src.data.loader import (
    load_data_from_disk,
    append_new_data,
)
from src.data.processor import DataProcessor
from src.ui.filters import render_filters
from src.ui.metrics import render_metrics, render_insights
from src.ui.layout import render_charts
from src.auth.session import require_login, render_user_sidebar, is_admin
from src.ui.error_boundary import page_guard

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(**PAGE_CONFIG)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Global text default (prevents invisible/black text after blur) ── */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    .stMarkdown, .stText, p, span, label, div {
        color: #0D1B17;
    }

    /* ── Main area ── */
    [data-testid="stAppViewContainer"] > .main { background: #FAFCFB; }
    [data-testid="stMain"] { background: #FAFCFB; }
    [data-testid="stHeader"] { background: #FAFCFB !important; }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1400px; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] { background: #FFFFFF !important; border-right: 1px solid rgba(0,0,0,0.06); }
    [data-testid="stSidebar"] * { color: #0D1B17; }
    [data-testid="stSidebar"] label { color: #4A5752 !important; font-size: 13px !important; }

    /* ── Inputs / Select / Multiselect / DateInput / NumberInput / TextArea ── */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div,
    .stMultiSelect [data-baseweb="select"] > div,
    [data-baseweb="input"], [data-baseweb="select"] {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.35) !important;
        border-radius: 8px !important;
    }
    .stTextInput input:hover, .stNumberInput input:hover, .stDateInput input:hover,
    .stSelectbox [data-baseweb="select"] > div:hover,
    .stMultiSelect [data-baseweb="select"] > div:hover {
        border-color:#0D1B17 !important;
        box-shadow: 0 0 0 2px rgba(0,229,160,0.15) !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stDateInput input:focus,
    .stTextArea textarea:focus {
        border-color:#0D1B17 !important;
        box-shadow: 0 0 0 2px rgba(0,229,160,0.25) !important;
        outline: none !important;
    }
    /* Dropdown menu (BaseWeb popover) */
    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.25) !important;
    }
    [data-baseweb="menu"] li, [role="option"] { color: #0D1B17 !important; background: #FFFFFF !important; }
    [data-baseweb="menu"] li:hover, [role="option"]:hover,
    [role="option"][aria-selected="true"] { background: rgba(0,229,160,0.15) !important; color: #0D1B17 !important; }

    /* SVG icons inside inputs (chevrons, calendar, clear) */
    [data-baseweb="select"] svg, [data-baseweb="input"] svg,
    .stDateInput svg { fill: #00B884 !important; color:#0D1B17 !important; }

    /* ── Upload area — discreta ── */
    [data-testid="stSidebar"] [data-testid="stFileUploader"] {
        background: #F2F7F5 !important;
        border: 1px dashed rgba(0,184,132,0.45) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: transparent !important;
        padding: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] span {
        font-size: 11.5px !important;
        color: #4A5752 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] small {
        font-size: 10px !important;
        color:#4A5752 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
        font-size: 11px !important;
        padding: 4px 12px !important;
        background: rgba(0,229,160,0.25) !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.45) !important;
        border-radius: 6px !important;
    }

    /* ── Expander ── */
    [data-testid="stExpander"] { background: #FFFFFF !important; border: 1px solid rgba(0,0,0,0.08) !important; border-radius: 10px !important; }
    [data-testid="stExpander"] summary { font-size: 13px !important; color: #0D1B17 !important; }
    [data-testid="stExpander"] summary:hover { color: #00805C !important; }

    /* ── Buttons ── */
    .stButton > button, .stDownloadButton > button {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid #00B884 !important;
        border-radius: 8px !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        transition: all 0.18s ease !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background: rgba(0,229,160,0.20) !important;
        color: #00805C !important;
        border-color:#0D1B17 !important;
        box-shadow: 0 0 0 3px rgba(0,229,160,0.15) !important;
    }
    .stButton > button:focus, .stButton > button:active,
    .stDownloadButton > button:focus, .stDownloadButton > button:active {
        background: rgba(0,229,160,0.28) !important;
        color: #0D1B17 !important;
        border-color:#0D1B17 !important;
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(0,229,160,0.30) !important;
    }

    /* ── Multiselect tags ── */
    [data-baseweb="tag"] {
        background: rgba(0,229,160,0.25) !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.4) !important;
    }
    [data-baseweb="tag"] * { color: #0D1B17 !important; }

    /* ── Slider ── */
    [data-baseweb="slider"] [role="slider"] { background: #00B884 !important; border-color:#0D1B17 !important; }

    /* ── DataFrame / Tables ── */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        background: #FFFFFF !important;
        color: #0D1B17 !important;
        border: 1px solid rgba(0,184,132,0.20) !important;
        border-radius: 8px;
    }
    [data-testid="stDataFrame"] * { color: #0D1B17 !important; }
    [data-testid="stDataFrame"] thead th {
        background: #F2F7F5 !important;
        color: #0D1B17 !important;
        border-bottom: 1px solid rgba(0,184,132,0.35) !important;
    }
    [data-testid="stDataFrame"] tbody tr:hover td { background: rgba(0,229,160,0.10) !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid rgba(0,184,132,0.20); }
    .stTabs [data-baseweb="tab"] { color: #4A5752 !important; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #00805C !important; }
    .stTabs [data-baseweb="tab-highlight"] { background: #00B884 !important; }

    /* ── Alerts ── */
    [data-testid="stAlert"] { color: #0D1B17 !important; }

    /* ── Metric ── */
    [data-testid="stMetricValue"] { color: #0D1B17 !important; }
    [data-testid="stMetricLabel"] { color: #4A5752 !important; }
    [data-testid="stMetricDelta"] { color: #00805C !important; }

    /* ── Divider ── */
    hr { border-color: rgba(0,184,132,0.20) !important; }

    /* ── Links ── */
    a, a:visited { color: #00805C !important; }
    a:hover { color:#0D1B17 !important; }

    /* ── Vega/Altair chart tooltips ── */
    #vg-tooltip-element {
        background: #061210 !important;
        border: 1px solid #00B884 !important;
        border-radius: 12px !important;
        padding: 14px 18px !important;
        box-shadow:
            0 0 0 1px rgba(0,229,160,0.15),
            0 0 28px rgba(0,184,132,0.55),
            0 0 60px rgba(0,184,132,0.20),
            0 8px 28px rgba(0,0,0,0.90) !important;
        font-family: 'Inter', monospace !important;
        min-width: 170px !important;
        pointer-events: none !important;
        z-index: 9999 !important;
    }
    #vg-tooltip-element h2 {
        color: #00E5A0 !important;
        font-size: 10px !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 1.2px !important;
        margin: 0 0 10px 0 !important;
        padding-bottom: 7px !important;
        border-bottom: 1px solid rgba(0,229,160,0.25) !important;
    }
    #vg-tooltip-element table {
        border-spacing: 0 !important;
        border-collapse: collapse !important;
        width: 100% !important;
    }
    #vg-tooltip-element tr {
        border-bottom: 1px solid rgba(0,184,132,0.08) !important;
    }
    #vg-tooltip-element tr:last-child {
        border-bottom: none !important;
    }
    #vg-tooltip-element td {
        padding: 5px 0 !important;
        font-size: 13px !important;
        line-height: 1.4 !important;
    }
    #vg-tooltip-element td.key {
        color: #5FF6C6 !important;
        font-size: 10.5px !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.7px !important;
        padding-right: 20px !important;
        opacity: 0.80 !important;
        white-space: nowrap !important;
    }
    #vg-tooltip-element td.value {
        color: #00FF9C !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        letter-spacing: -0.3px !important;
        text-align: right !important;
        text-shadow: 0 0 10px rgba(0,255,156,0.50) !important;
    }

    /* ── Streamlit help (ⓘ) tooltips ── */
    [data-baseweb="tooltip"] > div {
        background: #061210 !important;
        border: 1px solid #00B884 !important;
        border-radius: 10px !important;
        box-shadow:
            0 0 22px rgba(0,184,132,0.50),
            0 6px 20px rgba(0,0,0,0.80) !important;
        padding: 10px 14px !important;
        max-width: 320px !important;
    }
    [data-baseweb="tooltip"] * {
        color: #00E5A0 !important;
        font-size: 12.5px !important;
        line-height: 1.6 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Components ────────────────────────────────────────────────────────────────

def _header(total_records: int | None = None) -> None:
    if total_records is not None:
        subtitle = (
            f'Base carregada automaticamente — '
            f'<code style="background:rgba(0,229,160,0.18);padding:2px 7px;'
            f'border-radius:4px;font-size:11px;color:#4A5752">'
            f'{total_records:,} registros</code>'
        )
    else:
        subtitle = "Dashboard de Análise de Defeitos e Remontes do Acabamento."

    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(0,0,0,0.06);margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">🔍 Análise de Defeitos</span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};background:rgba(0,229,160,0.18);
                             padding:3px 10px;border-radius:20px;border:1px solid rgba(0,229,160,0.3)">
                    Controle de Qualidade
                </span>
            </div>
            <p style="color:{COLORS['text_muted']};font-size:13px;margin:5px 0 0">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_import_sidebar(df_total_rows: int) -> None:
    """
    Expander discreto na sidebar para importar novos registros diários.
    Faz append na bd_principal.xlsx sem substituir dados existentes.
    """
    st.sidebar.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Info rápida da base
    st.sidebar.markdown(
        f'<div style="font-size:10.5px;color:#00805C;padding:6px 8px;'
        f'border-radius:6px;background:rgba(0,229,160,0.06);'
        f'border:1px solid rgba(0,229,160,0.15);margin-bottom:8px">'
        f'<span style="color:#00805C">●</span> '
        f'<span style="color:#4A5752">{df_total_rows:,} registros na base</span></div>',
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("➕ Importar novos registros"):
        st.markdown(
            '<p style="font-size:11.5px;color:#4A5752;margin-bottom:8px;line-height:1.5">'
            'Selecione o arquivo do dia para adicionar registros novos.<br>'
            'Duplicatas são ignoradas automaticamente.</p>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "arquivo_diario",
            type=["xlsx", "xls"],
            key="import_uploader",
            label_visibility="collapsed",
            help="Arquivo .xlsx com os novos registros do dia",
        )
        if uploaded is not None:
            upload_key = (uploaded.name, uploaded.size)
            if st.session_state.get("last_processed_file") != upload_key:
                with st.spinner("Importando…"):
                    result = append_new_data(uploaded)
                if result is not None:
                    st.session_state["last_processed_file"] = upload_key
                    if result["added"] > 0:
                        st.session_state["import_message"] = {
                            "type": "success",
                            "text": f"✅ **{result['added']}** novos registros adicionados\n\n"
                                    f"{'⚠️ ' + str(result['duplicates']) + ' duplicatas ignoradas  ' if result['duplicates'] else ''}"
                                    f"Base total: **{result['total']:,}** registros"
                        }
                    else:
                        st.session_state["import_message"] = {
                            "type": "info",
                            "text": f"ℹ️ Nenhum registro novo encontrado.\n\n"
                                    f"{result['duplicates']} registro(s) já existiam na base."
                        }
                    # Recarrega a base atualizada na session_state
                    df_updated = load_data_from_disk()
                    if df_updated is not None:
                        st.session_state["df"] = df_updated
                    st.rerun()

            # Exibe a mensagem persistida do processamento
            import_msg = st.session_state.get("import_message")
            if import_msg:
                if import_msg["type"] == "success":
                    st.success(import_msg["text"])
                else:
                    st.info(import_msg["text"])
        else:
            # Limpa o estado quando nenhum arquivo está carregado
            st.session_state.pop("last_processed_file", None)
            st.session_state.pop("import_message", None)


def _render_first_upload_sidebar() -> None:
    """
    Exibido apenas quando bd_principal.xlsx ainda não existe (primeira vez).
    Cria a base a partir do arquivo inicial.
    """
    st.sidebar.markdown(
        '<p style="font-size:11px;color:#4A5752;letter-spacing:0.4px;margin-bottom:6px">'
        '📂 Carga inicial da base</p>',
        unsafe_allow_html=True,
    )
    uploaded = st.sidebar.file_uploader(
        "planilha",
        type=["xlsx", "xls"],
        key="first_upload",
        label_visibility="collapsed",
        help="Arquivo .xlsx com todos os registros históricos",
    )
    if uploaded is not None:
        with st.sidebar:
            with st.spinner("Criando base…"):
                result = append_new_data(uploaded)
        if result is not None:
            df = load_data_from_disk()
            if df is not None:
                st.session_state["df"] = df
                st.rerun()


def _render_upload_placeholder() -> None:
    descricao = (
        "Faça o upload da planilha histórica pela barra lateral.<br>"
        "Ela será salva automaticamente e carregada a cada acesso."
        if is_admin()
        else "Aguarde um administrador realizar a carga inicial da base de dados."
    )
    st.markdown(
        f"""
        <div style="
            display:flex; flex-direction:column; align-items:center;
            justify-content:center; min-height:44vh; text-align:center;
            gap:10px;
        ">
            <div style="font-size:36px; opacity:0.18">📊</div>
            <p style="
                font-size:15px; font-weight:600;
                color:{COLORS['text_primary']}; margin:0;
            ">Base principal não encontrada</p>
            <p style="
                font-size:13px; color:{COLORS['text_subtle']};
                margin:0; max-width:340px; line-height:1.6;
            ">
                {descricao}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _divider() -> None:
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


# ── Auto-load na inicialização ────────────────────────────────────────────────

def _bootstrap() -> None:
    """
    Tenta carregar bd_principal.xlsx na session_state no primeiro acesso.
    Executa apenas uma vez por sessão (guarda flag 'disk_load_attempted').
    """
    if "disk_load_attempted" not in st.session_state:
        st.session_state["disk_load_attempted"] = True
        df = load_data_from_disk()
        if df is not None:
            st.session_state["df"] = df


# ── Main ──────────────────────────────────────────────────────────────────────

@page_guard
def main() -> None:

    # ── Portão de autenticação (tela de proteção) ─────────────────────────────
    require_login()
    render_user_sidebar()

    _bootstrap()

    # ── Sem dados: base ainda não existe → pede carga inicial ─────────────────
    if "df" not in st.session_state:
        _header()
        if is_admin():
            _render_first_upload_sidebar()
        _render_upload_placeholder()
        return

    # ── Dados disponíveis: fluxo normal ───────────────────────────────────────
    df = st.session_state["df"]

    _header(total_records=len(df))

    # Sidebar: filtros + expander de importação (apenas administradores)
    filtered_df = render_filters(df)
    if is_admin():
        _render_import_sidebar(df_total_rows=len(df))

    if filtered_df.empty:
        st.warning("⚠️ Nenhum registro encontrado com os filtros aplicados. Ajuste-os na barra lateral.")
        return

    processor = DataProcessor(filtered_df)

    render_metrics(processor)
    _divider()
    render_insights(processor)
    _divider()
    render_charts(processor, df)


if __name__ == "__main__":
    main()
