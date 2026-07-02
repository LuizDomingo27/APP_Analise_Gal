# -*- coding: utf-8 -*-
"""
Pagina: Correção de Registros
Entry point do Streamlit multi-page.

Página isolada para corrigir valores digitados incorretamente na base
ativa (ex.: fornecedor com/sem acento, caractere especial). Afeta somente
a tabela registros_defeitos — nunca historico_cobrancas ou
pagamentos_concluidos.
"""

import streamlit as st

# Page config (deve ser o primeiro call Streamlit da pagina)
st.set_page_config(
    page_title="Correção de Registros",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config.settings import COLORS
from src.ui.records_editor import render_records_editor_page

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
    .stButton > button[kind="primary"]:hover {
        background: rgba(0,184,132,1.0) !important;
    }
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    hr { border-color: rgba(0,0,0,0.06) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _render_no_data_message() -> None:
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
                e faça a carga inicial da planilha histórica.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    if "df" not in st.session_state:
        _render_no_data_message()
        return

    render_records_editor_page()


main()
