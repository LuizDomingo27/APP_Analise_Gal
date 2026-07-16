"""
Análise de Defeitos de Produção — Streamlit App
Roteador / entrypoint: page config, injeção de CSS global, autenticação e
navbar no topo.

A navegação foi migrada da pasta pages/ (sidebar automática) para
st.navigation(position="top"), que renderiza a barra de navegação no topo.
Este arquivo funciona como roteador: envolve todas as páginas com o CSS
global, o portão de login e o cabeçalho de usuário, e então executa a
página atual. O conteúdo de cada tela mora nos scripts de pages/.
"""

import streamlit as st
from src.config.settings import PAGE_CONFIG
from src.auth.session import require_login, render_user_topbar, is_admin
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

    /* ── Sidebar removida (todos os componentes migraram para o corpo) ── */
    [data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    button[kind="headerNoPadding"][data-testid="stBaseButton-headerNoPadding"] {
        display: none !important;
    }

    /* ── Navbar (st.navigation position="top") centralizada ── */
    /* A linha da navbar é o container flex `oke` (div.e1lpckdq13), que já tem
       width:100%; basta centralizar seus itens. Alvo primário: a classe estável
       do Streamlit 1.58. Reforço estrutural: o único elemento cujo NETO é um
       stTopNavLinkContainer é essa mesma linha (os links ficam em wrappers
       intermediários), então este seletor casa só com ela — nunca com cada link. */
    [data-testid="stHeader"] .e1lpckdq13,
    [data-testid="stHeader"] :has(> * > [data-testid="stTopNavLinkContainer"]) {
        justify-content: center !important;
        gap: 4px !important;
    }

    /* ── Navbar — estilo "Pílula sólida" (aprovado) ──────────────────────── */
    /* Header: fundo branco, sombra suave e um traço de acento verde embaixo. */
    [data-testid="stHeader"] {
        background: #FFFFFF !important;
        box-shadow: inset 0 -2px 0 0 rgba(0,184,132,0.28),
                    0 4px 18px rgba(4,40,30,0.05) !important;
    }

    /* Cada link do topo (o <a> stTopNavLink) vira uma pílula. */
    [data-testid="stHeader"] [data-testid="stTopNavLink"] {
        border-radius: 11px !important;
        padding: 7px 13px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #5A6B64 !important;
        transition: background 0.16s ease, color 0.16s ease, box-shadow 0.16s ease !important;
    }
    [data-testid="stHeader"] [data-testid="stTopNavLink"] * { color: inherit !important; }

    /* Hover (item inativo): tinta verde suave. */
    [data-testid="stHeader"] [data-testid="stTopNavLink"]:not([aria-current="page"]):hover {
        background: rgba(0,201,150,0.12) !important;
        color: #00805C !important;
    }

    /* Item ativo: pílula verde gradiente, texto escuro, leve elevação. */
    [data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] {
        background: linear-gradient(135deg,#00E5A0,#00B884) !important;
        color: #04231B !important;
        font-weight: 600 !important;
        box-shadow: 0 3px 10px rgba(0,184,132,0.35) !important;
    }
    [data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] * {
        color: #04231B !important;
    }

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


# ── Router ────────────────────────────────────────────────────────────────────

@page_guard
def main() -> None:
    # ── Portão de autenticação (tela de proteção) ─────────────────────────────
    require_login()

    # ── Usuário logado + sair, no topo (substitui o cartão da sidebar) ────────
    render_user_topbar()

    # ── Páginas disponíveis (navbar no topo) ──────────────────────────────────
    # As páginas restritas a administradores só são registradas para admins,
    # de modo que usuários comuns nem veem o item na navbar.
    pages = [
        st.Page("pages/1_Dashboard.py", title="Análise de Defeitos", icon="🔍", default=True),
        st.Page("pages/2_Historico_Defeitos.py", title="Histórico de Defeitos", icon="🗂️"),
        st.Page("pages/3_Historico_Cobranca.py", title="Cobranças", icon="🗃️"),
        st.Page("pages/4_Defeitos_Imagens.py", title="Imagens de Defeitos", icon="🖼️"),
    ]
    if is_admin():
        pages.append(
            st.Page("pages/5_Editar_Registros.py", title="Editar Registros", icon="🛠️")
        )
        pages.append(
            st.Page("pages/6_Gerenciar_Usuarios.py", title="Usuários", icon="👥")
        )

    nav = st.navigation(pages, position="top")
    nav.run()


if __name__ == "__main__":
    main()
