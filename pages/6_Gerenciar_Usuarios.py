# -*- coding: utf-8 -*-
"""
Página: Gerenciamento de Usuários
Apenas acessível para administradores.
"""

import streamlit as st

from src.auth.session import require_login
from src.ui.error_boundary import page_guard
from src.ui.user_manager import render_user_manager_page

# CSS consistente com a identidade visual do app
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
    hr { border-color: rgba(0,0,0,0.06) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


@page_guard
def main() -> None:
    # 1. Garante que o usuário está logado
    user = require_login()

    # 2. Restrição de segurança: apenas admin pode visualizar
    if user.get("role") != "admin":
        st.error("Acesso negado. Esta página é restrita a administradores.")
        st.stop()

    # 3. Renderiza a UI do gerenciamento
    render_user_manager_page()


if __name__ == "__main__":
    main()
