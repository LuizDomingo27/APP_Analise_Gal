# -*- coding: utf-8 -*-
"""
Página: Análise de Defeitos (dashboard principal).

Página executada pelo roteador (app.py) via st.navigation. O page config,
o CSS global e o portão de login/navbar de usuário ficam no roteador; aqui
mora apenas o conteúdo do dashboard.

Carregamento de dados:
  • Startup normal   → lê a base direto do disco (load_data_from_disk)
  • Primeira vez     → exibe uploader para criar a base (comportamento legado)
  • Importar novos   → expander discreto no corpo principal faz append diário
"""

import streamlit as st
from src.config.settings import COLORS
from src.data.loader import (
    load_data_from_disk,
    append_new_data,
)
from src.data.processor import DataProcessor
from src.ui.filters import render_filters
from src.ui.metrics import render_metrics, render_insights
from src.ui.layout import render_charts
from src.auth.session import require_login, is_admin
from src.ui.error_boundary import page_guard


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


def _render_import_panel(df_total_rows: int) -> None:
    """
    Expander discreto no corpo principal (abaixo da navbar) para importar novos
    registros diários. Faz append na base sem substituir dados existentes.
    """
    with st.expander("➕ Importar novos registros"):
        # Info rápida da base
        st.markdown(
            f'<div style="font-size:10.5px;color:#00805C;padding:6px 8px;'
            f'border-radius:6px;background:rgba(0,229,160,0.06);'
            f'border:1px solid rgba(0,229,160,0.15);margin-bottom:8px">'
            f'<span style="color:#00805C">●</span> '
            f'<span style="color:#4A5752">{df_total_rows:,} registros na base</span></div>',
            unsafe_allow_html=True,
        )
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


def _render_first_upload_panel() -> None:
    """
    Exibido apenas quando a base ainda não existe (primeira vez).
    Cria a base a partir do arquivo inicial, no corpo principal.
    """
    st.markdown(
        '<p style="font-size:11px;color:#4A5752;letter-spacing:0.4px;margin-bottom:6px">'
        '📂 Carga inicial da base</p>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader(
        "planilha",
        type=["xlsx", "xls"],
        key="first_upload",
        label_visibility="collapsed",
        help="Arquivo .xlsx com todos os registros históricos",
    )
    if uploaded is not None:
        with st.spinner("Criando base…"):
            result = append_new_data(uploaded)
        if result is not None:
            df = load_data_from_disk()
            if df is not None:
                st.session_state["df"] = df
                st.rerun()


def _render_upload_placeholder() -> None:
    descricao = (
        "Faça o upload da planilha histórica no campo acima.<br>"
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
    Tenta carregar a base na session_state no primeiro acesso.
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
    require_login()

    _bootstrap()

    # ── Sem dados: base ainda não existe → pede carga inicial ─────────────────
    if "df" not in st.session_state:
        _header()
        if is_admin():
            _render_first_upload_panel()
        _render_upload_placeholder()
        return

    # ── Dados disponíveis: fluxo normal ───────────────────────────────────────
    df = st.session_state["df"]

    _header(total_records=len(df))

    # Corpo principal: filtros + expander de importação (apenas administradores)
    filtered_df = render_filters(df)
    if is_admin():
        _render_import_panel(df_total_rows=len(df))

    _divider()

    if filtered_df.empty:
        st.warning("⚠️ Nenhum registro encontrado com os filtros aplicados. Ajuste os filtros acima.")
        return

    processor = DataProcessor(filtered_df)

    render_metrics(processor)
    _divider()
    render_insights(processor)
    _divider()
    render_charts(processor, df)


main()
