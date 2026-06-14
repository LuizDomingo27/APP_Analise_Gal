# -*- coding: utf-8 -*-
"""
Pagina: Cobranca de Fornecedores
Entry point do Streamlit multi-page.
Carrega dados da sessao e delega renderizacao para src/ui/cobranca.py.

CHANGELOG v10:
- Removido: import de cnpj_loader e carregamento da base Bd_Cnpj.xlsx.
- Removido: _render_sidebar_status com status da base CNPJ (não mais necessário).
- Simplificado: render_cobranca_page não recebe mais cnpj_db.
"""

import streamlit as st

# Page config (deve ser o primeiro call Streamlit da pagina)
st.set_page_config(
    page_title="Cobranca de Fornecedores",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Importacoes internas (apos set_page_config)
from src.config.settings import COLORS
from src.ui.cobranca import render_cobranca_page

# CSS consistente com a identidade visual do app principal
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] > .main { background: #0D0D1A; }
    [data-testid="stMain"]                      { background: #0D0D1A; }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }
    [data-testid="stSidebar"] {
        background: #0A0A18 !important;
        border-right: 1px solid rgba(255,255,255,0.06);
    }
    [data-testid="stSidebar"] label {
        color: #9898BB !important;
        font-size: 13px !important;
    }
    .stButton > button {
        background: rgba(83,74,183,0.15) !important;
        color: #B8B0FF !important;
        border: 1px solid rgba(83,74,183,0.35) !important;
        border-radius: 8px !important;
        font-size: 12px !important;
    }
    .stButton > button:hover {
        background: rgba(83,74,183,0.28) !important;
        border-color: rgba(83,74,183,0.6) !important;
    }
    .stButton > button[kind="primary"] {
        background: rgba(194,57,43,0.85) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(194,57,43,0.6) !important;
        font-weight: 600 !important;
        font-size: 13px !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: rgba(194,57,43,1.0) !important;
    }
    [data-testid="stExpander"] {
        background: rgba(255,255,255,0.02) !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 10px !important;
    }
    hr { border-color: rgba(255,255,255,0.06) !important; }
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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
                e faça a carga inicial da planilha histórica.<br>
                A base será salva automaticamente e carregada
                em todos os acessos futuros.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar_info(total_records: int) -> None:
    """Exibe informações básicas da base na sidebar."""
    st.sidebar.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:#6868AA;margin-bottom:10px">📊 Status</p>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        '<div style="font-size:10.5px;color:#1D9E75;padding:6px 8px;'
        'border-radius:6px;background:rgba(29,158,117,0.08);'
        'border:1px solid rgba(29,158,117,0.2);margin-bottom:8px">'
        '&#10003; Base carregada automaticamente</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        f'<div style="font-size:10px;color:#3C3C70;margin-top:8px;'
        f'padding:6px 8px;border-top:1px solid rgba(255,255,255,0.04)">'
        f'🗃️ {total_records:,} registros na base</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if "df" not in st.session_state:
        _render_no_data_message()
        return

    df = st.session_state["df"]

    _render_sidebar_info(total_records=len(df))

    render_cobranca_page(df)


main()
