"""
Análise de Defeitos de Produção — Streamlit App
Entry point: page config, CSS injection, top-level orchestration.

Carregamento de dados (novo fluxo):
  • Startup normal   → lê bd_principal.xlsx direto da pasta dataset/
  • Primeira vez     → exibe uploader para criar a base (comportamento legado)
  • Importar novos   → expander discreto na sidebar faz append diário
"""

import streamlit as st
from src.config.settings import PAGE_CONFIG, COLORS, BD_PRINCIPAL
from src.data.loader import (
    load_data_from_disk,
    load_data_from_upload,
    append_new_data,
)
from src.data.processor import DataProcessor
from src.ui.filters import render_filters
from src.ui.metrics import render_metrics, render_insights
from src.ui.layout import render_charts

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(**PAGE_CONFIG)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Main area ── */
    [data-testid="stAppViewContainer"] > .main { background: #0D0D1A; }
    [data-testid="stMain"] { background: #0D0D1A; }
    .main .block-container { padding-top: 1.5rem; padding-bottom: 3rem; max-width: 1400px; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] { background: #0A0A18 !important; border-right: 1px solid rgba(255,255,255,0.06); }
    [data-testid="stSidebar"] label { color: #9898BB !important; font-size: 13px !important; }
    [data-testid="stSidebar"] .stMultiSelect > div { background: rgba(255,255,255,0.04) !important; }
    [data-testid="stSidebar"] [data-testid="stDateInput"] input { background: rgba(255,255,255,0.04) !important; color: #E8E8FF !important; }

    /* ── Upload area — discreta ── */
    [data-testid="stSidebar"] [data-testid="stFileUploader"] {
        background: rgba(255,255,255,0.02) !important;
        border: 1px dashed rgba(104,104,170,0.22) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: transparent !important;
        padding: 8px !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] span {
        font-size: 11.5px !important;
        color: #6868AA !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] small {
        font-size: 10px !important;
        color: #4A4A80 !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] button {
        font-size: 11px !important;
        padding: 4px 12px !important;
        background: rgba(83,74,183,0.18) !important;
        color: #9898BB !important;
        border: 1px solid rgba(83,74,183,0.28) !important;
        border-radius: 6px !important;
    }

    /* ── Expander ── */
    [data-testid="stExpander"] { background: rgba(255,255,255,0.02) !important; border: 1px solid rgba(255,255,255,0.07) !important; border-radius: 10px !important; }
    [data-testid="stExpander"] summary { font-size: 13px !important; color: #9898BB !important; }

    /* ── Plotly chart bg ── */
    .js-plotly-plot .plotly .main-svg { background: transparent !important; }

    /* ── Buttons ── */
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

    /* ── Multiselect tags ── */
    [data-baseweb="tag"] { background: rgba(83,74,183,0.25) !important; }

    /* ── Divider ── */
    hr { border-color: rgba(255,255,255,0.06) !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Components ────────────────────────────────────────────────────────────────

def _header(total_records: int | None = None) -> None:
    if total_records is not None:
        subtitle = (
            f'Base carregada automaticamente — '
            f'<code style="background:rgba(83,74,183,0.18);padding:2px 7px;'
            f'border-radius:4px;font-size:11px;color:#C8C0F0">'
            f'{total_records:,} registros</code>'
        )
    else:
        subtitle = "Dashboard de Análise de Defeitos e Remontes do Acabamento."

    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">🔍 Análise de Defeitos</span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};background:rgba(83,74,183,0.18);
                             padding:3px 10px;border-radius:20px;border:1px solid rgba(83,74,183,0.3)">
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
        f'<div style="font-size:10.5px;color:#3C3C70;padding:6px 8px;'
        f'border-radius:6px;background:rgba(29,158,117,0.06);'
        f'border:1px solid rgba(29,158,117,0.15);margin-bottom:8px">'
        f'<span style="color:#1D9E75">●</span> '
        f'<span style="color:#6868AA">{df_total_rows:,} registros na base</span></div>',
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("➕ Importar novos registros"):
        st.markdown(
            '<p style="font-size:11.5px;color:#6868AA;margin-bottom:8px;line-height:1.5">'
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
        '<p style="font-size:11px;color:#6868AA;letter-spacing:0.4px;margin-bottom:6px">'
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
                Faça o upload da planilha histórica pela barra lateral.<br>
                Ela será salva automaticamente e carregada a cada acesso.
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

def main() -> None:

    _bootstrap()

    # ── Sem dados: base ainda não existe → pede carga inicial ─────────────────
    if "df" not in st.session_state:
        _header()
        _render_first_upload_sidebar()
        _render_upload_placeholder()
        return

    # ── Dados disponíveis: fluxo normal ───────────────────────────────────────
    df = st.session_state["df"]

    _header(total_records=len(df))

    # Sidebar: filtros + expander de importação
    filtered_df = render_filters(df)
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
