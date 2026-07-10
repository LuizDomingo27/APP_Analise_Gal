# -*- coding: utf-8 -*-
"""
UI da página Histórico de Defeitos — módulo isolado.

Estrutura da página (de cima para baixo):
  1. Cabeçalho
  2. Upload dos dados do dia (somente administradores) — na própria página,
     não na sidebar (a sidebar já é usada pela cobrança na página principal).
  3. Cards de KPIs + faixa de insights (mesmos da página principal).
  4. Filtros (selectbox de oficina/fornecedor + período) logo abaixo dos cards.
  5. Apenas gráficos (sem tabelas de dados).
  6. Formulário de correção de nome de fornecedor (somente administradores):
     pesquisa o nome atual e grava a grafia corrigida em todo o histórico.

Toda a página é defensiva: dados ausentes ou falhas de banco resultam em
mensagens amigáveis, nunca em traceback na tela.
"""

import pandas as pd
import streamlit as st

from src.auth.session import is_admin
from src.charts import builder
from src.charts.render import echart
from src.config.settings import COLS, COLORS
from src.data.historico_defeitos import (
    append_historico,
    get_supplier_counts,
    load_historico,
    rename_supplier,
)
from src.data.processor import DataProcessor
from src.ui.metrics import render_insights, render_metrics


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def render_historico_page() -> None:
    _render_header()

    if is_admin():
        _render_upload_section()

    df = load_historico()
    if df is None or df.empty:
        _render_no_data_message()
        return

    # Cards ficam VISUALMENTE acima dos filtros, mas precisam refletir o
    # dataset filtrado. Reservamos um container para eles agora e o
    # preenchemos depois de ler os widgets de filtro (mais abaixo na tela).
    cards_area = st.container()

    filtered = _render_filters(df)

    with cards_area:
        if filtered.empty:
            st.warning(
                "⚠️ Nenhum registro encontrado com os filtros selecionados. "
                "Ajuste a oficina ou o período abaixo."
            )
        else:
            processor = DataProcessor(filtered)
            render_metrics(processor)
            _spacer(6)
            render_insights(processor)

    if not filtered.empty:
        _spacer(10)
        _render_charts_only(DataProcessor(filtered))

    if is_admin():
        _spacer(18)
        _render_supplier_edit_form()


# ══════════════════════════════════════════════════════════════════════════════
# Cabeçalho
# ══════════════════════════════════════════════════════════════════════════════

def _render_header() -> None:
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(0,0,0,0.06);margin-bottom:1.4rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">
                    🗂️ Histórico de Defeitos
                </span>
                <span style="font-size:12px;color:{COLORS['text_subtle']};
                             background:rgba(0,229,160,0.18);padding:3px 10px;
                             border-radius:20px;border:1px solid rgba(0,229,160,0.3)">
                    Registro Permanente
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Upload (na própria página) — administradores
# ══════════════════════════════════════════════════════════════════════════════

def _render_upload_section() -> None:
    with st.expander("➕ Importar registros do dia para o histórico", expanded=False):
        st.markdown(
            f"<p style='font-size:12.5px;color:{COLORS['text_muted']};margin:0 0 10px;line-height:1.6'>"
            "Selecione a planilha do dia (.xlsx). Os registros são adicionados ao "
            "histórico permanente. Datas já presentes são ignoradas automaticamente "
            "para evitar duplicação — <strong>nada é apagado</strong>.</p>",
            unsafe_allow_html=True,
        )

        uploaded = st.file_uploader(
            "planilha_historico",
            type=["xlsx", "xls"],
            key="historico_uploader",
            label_visibility="collapsed",
            help="Arquivo .xlsx com os registros do dia",
        )

        if uploaded is None:
            st.session_state.pop("historico_last_file", None)
            st.session_state.pop("historico_import_msg", None)
            return

        upload_key = (uploaded.name, uploaded.size)
        if st.session_state.get("historico_last_file") != upload_key:
            with st.spinner("Importando para o histórico…"):
                result = append_historico(uploaded)
            if result is not None:
                st.session_state["historico_last_file"] = upload_key
                if result["added"] > 0:
                    dup = (
                        f"⚠️ {result['duplicates']} registro(s) de datas já existentes ignorado(s).  "
                        if result["duplicates"]
                        else ""
                    )
                    st.session_state["historico_import_msg"] = {
                        "type": "success",
                        "text": f"✅ **{result['added']}** novo(s) registro(s) adicionado(s) ao histórico.\n\n"
                                f"{dup}Total no histórico: **{result['total']:,}** registros.",
                    }
                else:
                    st.session_state["historico_import_msg"] = {
                        "type": "info",
                        "text": f"ℹ️ Nenhum registro novo. As {result['duplicates']} linha(s) "
                                "pertencem a datas que já estavam no histórico.",
                    }
                st.rerun()

        msg = st.session_state.get("historico_import_msg")
        if msg:
            (st.success if msg["type"] == "success" else st.info)(msg["text"])


# ══════════════════════════════════════════════════════════════════════════════
# Filtros (abaixo dos cards)
# ══════════════════════════════════════════════════════════════════════════════

def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Selectbox de oficina + período. Retorna o DataFrame filtrado."""
    st.markdown(
        f"<p style='font-size:11px;text-transform:uppercase;letter-spacing:1px;"
        f"color:{COLORS['text_muted']};margin:0 0 8px'>⚙️ Filtros</p>",
        unsafe_allow_html=True,
    )

    suppliers = sorted(df[COLS["supplier"]].dropna().unique().tolist())
    min_date = df[COLS["date"]].min().date()
    max_date = df[COLS["date"]].max().date()

    col_of, col_dt = st.columns([1, 1])
    with col_of:
        oficina = st.selectbox(
            "🏭 Oficina (Fornecedor)",
            options=["Todas as oficinas"] + suppliers,
            key="historico_filter_supplier",
        )
    with col_dt:
        date_range = st.date_input(
            "📅 Período",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            format="DD/MM/YYYY",
            key="historico_filter_dates",
        )

    filtered = df
    if oficina != "Todas as oficinas":
        filtered = filtered[filtered[COLS["supplier"]] == oficina]

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[
            (filtered[COLS["date"]].dt.date >= start)
            & (filtered[COLS["date"]].dt.date <= end)
        ]

    return filtered.copy()


# ══════════════════════════════════════════════════════════════════════════════
# Gráficos (sem tabelas)
# ══════════════════════════════════════════════════════════════════════════════

def _render_charts_only(processor: DataProcessor) -> None:
    # ── Distribuição ─────────────────────────────────────────────────────────
    _section("Distribuição de Defeitos", "🔍")
    c1, c2 = st.columns(2)
    with c1:
        _chart_label("Top 10 — local do defeito")
        echart(builder.bar_location(processor.by_location(), 10), key="hist_bar_location")
    with c2:
        _chart_label("Tipo de defeito")
        _defect_legend()
        echart(builder.donut_defect_type(processor.by_defect_type()), key="hist_donut_defect")

    # ── Evolução temporal ────────────────────────────────────────────────────
    _section("Evolução Temporal", "📅")
    _chart_label("Defeitos por dia")
    echart(builder.area_defects_by_date(processor.by_date()), key="hist_area_defects")
    _chart_label("Custo de remonte por dia (R$)")
    echart(builder.area_cost_by_date(processor.by_date_cost()), key="hist_area_cost")

    # ── Análise por fornecedor ───────────────────────────────────────────────
    _section("Análise por Oficina", "🏭")
    c3, c4 = st.columns(2)
    with c3:
        _chart_label("Top 10 — quantidade de defeitos")
        echart(builder.bar_supplier_quantity(processor.by_supplier_quantity(10)), key="hist_sup_qty")
    with c4:
        _chart_label("Top 10 — custo de remonte (R$)")
        echart(builder.bar_supplier_cost(processor.by_supplier_cost(10)), key="hist_sup_cost")

    _spacer(8)
    c5, c6 = st.columns(2)
    with c5:
        _chart_label("Top 10 — taxa média de remonte (%)")
        echart(builder.bar_supplier_rate(processor.by_supplier_rate(10)), key="hist_sup_rate")
    with c6:
        _chart_label("Top 12 — combinações Local × Defeito")
        _defect_legend()
        echart(builder.bar_key_combinations(processor.by_key(12)), key="hist_key_combos")


# ══════════════════════════════════════════════════════════════════════════════
# Formulário: correção de nome de fornecedor — administradores
# ══════════════════════════════════════════════════════════════════════════════

def _render_supplier_edit_form() -> None:
    _section("Correção de Nome de Oficina", "✏️")
    st.markdown(
        f"<p style='font-size:12.5px;color:{COLORS['text_muted']};margin:0 0 14px;line-height:1.6'>"
        "Pesquise o nome do fornecedor que precisa de correção (ex.: acento ou "
        "grafia diferente) e grave o nome correto. A correção é aplicada a "
        "<strong>todos</strong> os registros do histórico com aquele nome. "
        "Nenhum dado é apagado — apenas o nome é ajustado.</p>",
        unsafe_allow_html=True,
    )

    try:
        df_sup = get_supplier_counts()
    except Exception as exc:  # noqa: BLE001 — fronteira defensiva local
        st.error(f"⚠️ Não foi possível carregar os fornecedores: {exc}")
        return

    if df_sup.empty:
        st.info("Nenhum fornecedor cadastrado no histórico ainda.")
        return

    value_options = df_sup["valor"].tolist()

    col_old, col_new = st.columns(2)
    with col_old:
        old_value = st.selectbox(
            "Nome atual (a corrigir)",
            options=value_options,
            format_func=lambda v: f"{v}  —  {int(df_sup.loc[df_sup['valor'] == v, 'qtd'].iloc[0]):,} registro(s)",
            key="historico_rename_old",
        )
    with col_new:
        new_value = st.text_input(
            "Nome correto",
            value=old_value or "",
            key="historico_rename_new",
            help="Edite a grafia correta (acentos, espaços, caixa) e confirme abaixo.",
        )

    affected = (
        int(df_sup.loc[df_sup["valor"] == old_value, "qtd"].iloc[0])
        if old_value in value_options
        else 0
    )

    _spacer(6)
    disabled = not new_value or not new_value.strip() or new_value == old_value
    if st.button(
        f"✅ Aplicar correção a {affected:,} registro(s)",
        type="primary",
        disabled=disabled,
        key="historico_rename_apply",
    ):
        try:
            with st.spinner("Atualizando registros…"):
                n = rename_supplier(old_value, new_value.strip())
        except ValueError as exc:
            st.warning(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — fronteira defensiva local
            st.error(f"⚠️ Não foi possível aplicar a correção: {exc}")
            return

        if n:
            st.success(f'✅ {n:,} registro(s) atualizado(s): "{old_value}" → "{new_value.strip()}".')
            st.cache_data.clear()
            st.rerun()
        else:
            st.warning("Nenhum registro foi alterado.")


# ══════════════════════════════════════════════════════════════════════════════
# Estado vazio
# ══════════════════════════════════════════════════════════════════════════════

def _render_no_data_message() -> None:
    descricao = (
        "Use o campo <strong>Importar registros do dia</strong> acima para "
        "iniciar o histórico."
        if is_admin()
        else "Aguarde um administrador importar os primeiros registros."
    )
    st.markdown(
        f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;min-height:40vh;text-align:center;gap:10px">
            <div style="font-size:36px;opacity:0.18">🗂️</div>
            <p style="font-size:15px;font-weight:600;color:{COLORS['text_primary']};margin:0">
                Histórico ainda vazio
            </p>
            <p style="font-size:13px;color:{COLORS['text_subtle']};margin:0;max-width:360px;line-height:1.6">
                {descricao}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Helpers de layout (consistentes com src/ui/layout.py)
# ══════════════════════════════════════════════════════════════════════════════

def _section(title: str, icon: str = "📊") -> None:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin:2rem 0 0.7rem">
            <span style="font-size:18px">{icon}</span>
            <span style="font-size:15px;font-weight:600;color:{COLORS['text_primary']}">{title}</span>
            <div style="flex:1;height:1px;background:rgba(0,0,0,0.07);margin-left:6px"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _chart_label(text: str) -> None:
    st.markdown(
        f'<p style="font-size:12px;color:{COLORS["text_muted"]};'
        f'font-weight:500;margin:0 0 4px">{text}</p>',
        unsafe_allow_html=True,
    )


def _defect_legend() -> None:
    from src.config.settings import DEFECT_COLORS

    items = "".join(
        f'<span style="display:flex;align-items:center;gap:5px;'
        f'font-size:11px;color:{COLORS["text_muted"]}">'
        f'<span style="width:9px;height:9px;border-radius:2px;'
        f'background:{color};display:inline-block"></span>{label}</span>'
        for label, color in DEFECT_COLORS.items()
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:6px">{items}</div>',
        unsafe_allow_html=True,
    )


def _spacer(px: int) -> None:
    st.markdown(f"<div style='height:{px}px'></div>", unsafe_allow_html=True)
