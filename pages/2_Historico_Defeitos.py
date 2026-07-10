# -*- coding: utf-8 -*-
"""
Página: Histórico de Defeitos
Entry point do Streamlit multi-page.

Registro permanente e imutável de todos os defeitos importados diariamente.
Exibe os mesmos cards/insights e gráficos da página principal (sem tabelas),
com filtros de oficina e período. O upload e a correção de nomes de
fornecedores ficam na própria página e são restritos a administradores.
"""

import streamlit as st

# Page config (deve ser o primeiro call Streamlit da página)
st.set_page_config(
    page_title="Histórico de Defeitos",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.auth.session import render_user_sidebar, require_login
from src.ui.error_boundary import page_guard
from src.ui.historico_defeitos import render_historico_page

# CSS consistente com a identidade visual do app principal
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
    [data-testid="stSidebar"] label {
        color: #4A5752 !important;
        font-size: 13px !important;
    }
    /* ── Inputs / Select / DateInput / TextArea ── */
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
    /* ── Upload area ── */
    [data-testid="stFileUploader"] {
        background: #F2F7F5 !important;
        border: 1px dashed rgba(0,184,132,0.45) !important;
        border-radius: 8px !important;
    }
    /* ── Expander ── */
    [data-testid="stExpander"] {
        background: #FFFFFF !important;
        border: 1px solid rgba(0,0,0,0.08) !important;
        border-radius: 10px !important;
    }
    [data-testid="stExpander"] summary { font-size: 13px !important; color: #0D1B17 !important; }
    /* ── Buttons ── */
    .stButton > button {
        background: rgba(0,229,160,0.15) !important;
        color:#00805C !important;
        border: 1px solid rgba(0,229,160,0.35) !important;
        border-radius: 8px !important;
        font-size: 12px !important;
    }
    .stButton > button:hover {
        background: rgba(0,229,160,0.28) !important;
        border-color: rgba(0,229,160,0.6) !important;
    }
    .stButton > button[kind="primary"] {
        background: rgba(0,184,132,0.85) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(0,184,132,0.6) !important;
        font-weight: 600 !important;
        font-size: 13px !important;
    }
    .stButton > button[kind="primary"]:hover { background: rgba(0,184,132,1.0) !important; }
    [data-testid="stMetricValue"] { color: #0D1B17 !important; }
    hr { border-color: rgba(0,0,0,0.06) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


@page_guard
def main() -> None:
    require_login()
    render_user_sidebar()
    render_historico_page()


main()
