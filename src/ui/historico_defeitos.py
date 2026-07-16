# -*- coding: utf-8 -*-
"""
UI da página Histórico de Defeitos — módulo isolado.

Estrutura da página (de cima para baixo):
  1. Cabeçalho
  2. Upload dos dados do dia (somente administradores) — na própria página,
     não na sidebar (a sidebar já é usada pela cobrança na página principal).
  3. Cards de KPIs + faixa de insights (mesmos da página principal).
  4. Filtros (selectbox de oficina/fornecedor + período) logo abaixo dos cards,
     com a barra de exportação (Excel / PDF) na mesma linha.
  5. Apenas gráficos (sem tabelas de dados).
  6. Formulário de correção de nome de fornecedor (somente administradores):
     pesquisa o nome atual e grava a grafia corrigida em todo o histórico.

Toda a página é defensiva: dados ausentes ou falhas de banco resultam em
mensagens amigáveis, nunca em traceback na tela.
"""

import base64
import logging

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
from src.services.exporter import get_xlsx_bytes
from src.ui.layout import _VAR_TH, _VAR_TH_L, _row_bg, _td, _wrap_table
from src.ui.metrics import render_insights, render_metrics
from src.ui.preview import (
    _generate_defeitos_tabela_html,
    _generate_fornecedores_faixa_html,
)

logger = logging.getLogger(__name__)


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

    col_of, col_dt, col_exp = st.columns([1, 1, 1.4])
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

    filtered = filtered.copy()

    with col_exp:
        _render_export_bar(
            filtered, oficina, date_range,
            sem_filtro=len(filtered) == len(df), full_df=df,
        )

    return filtered


# ══════════════════════════════════════════════════════════════════════════════
# Exportação (mesma barra de ações da página principal, ao lado dos filtros)
# ══════════════════════════════════════════════════════════════════════════════

def _filters_description(oficina: str, date_range) -> str:
    periodo = ""
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        periodo = f" · {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
    return f"{oficina}{periodo}"


@st.cache_data(show_spinner=False)
def _xlsx_href(filtered: pd.DataFrame) -> str:
    """Data-URI do Excel agrupado por fornecedor. Propaga falhas de geração.

    Cacheado por conteúdo do DataFrame: a montagem do workbook formatado é
    custosa e rodava a cada rerun da página mesmo sem o usuário exportar.
    """
    xlsx_b64 = base64.b64encode(get_xlsx_bytes(filtered)).decode()
    return (
        "data:application/vnd.openxmlformats-officedocument"
        f".spreadsheetml.sheet;base64,{xlsx_b64}"
    )


def _render_export_bar(
    filtered: pd.DataFrame, oficina: str, date_range, sem_filtro: bool,
    full_df: pd.DataFrame | None = None,
) -> None:
    """
    Sem filtro (todos os registros): apenas Excel — o relatório PDF com todas as
    linhas do histórico é pesado demais para ser embutido no navegador.
    Com filtro: Excel + prévia/impressão em PDF (somente tabela, sem cards).

    A barra é renderizada dentro da linha de filtros, ANTES dos cards e dos
    gráficos. Por isso ela é uma fronteira defensiva: uma falha ao montar o
    Excel ou o HTML da prévia degrada apenas a exportação e nunca derruba o
    resto da página. `page_guard` não serve aqui — ele só captura
    DatabaseUnavailableError, e estas falhas são de geração de arquivo.
    """
    st.markdown(
        f"<p style='font-size:13.5px;font-weight:500;margin:0 0 8px;"
        f"color:{COLORS['text_primary']}'>📤 Exportar</p>",
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.caption("Nenhum registro para exportar.")
        return

    try:
        save_href = _xlsx_href(filtered)
    except Exception:  # noqa: BLE001 — fronteira defensiva local
        logger.exception("Falha ao gerar o Excel do histórico de defeitos")
        st.warning(
            "⚠️ Não foi possível gerar o arquivo de exportação agora. "
            "Ajuste os filtros ou tente novamente em instantes."
        )
        return

    html_page = None
    if not sem_filtro:
        try:
            html_page = _generate_defeitos_tabela_html(
                filtered, _filters_description(oficina, date_range)
            )
        except Exception:  # noqa: BLE001 — a prévia falha, o Excel continua válido
            logger.exception("Falha ao gerar a prévia em PDF do histórico de defeitos")

    if html_page is None:
        pdf_button  = ""
        script_html = ""
    else:
        html_b64 = base64.b64encode(html_page.encode("utf-8")).decode()
        pdf_button = (
            '<button class="abtn abtn-print" onclick="openPreview()">'
            "Prévia / Imprimir PDF</button>"
        )
        script_html = f"""
<script>
  const _HTML_B64 = "{html_b64}";
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
      console.error("Erro ao abrir prévia:", err);
      alert("Não foi possível abrir a prévia. Permita popups para este site.");
    }}
  }}
</script>"""

    components.html(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}
  .action-btns {{ display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; }}
  .abtn {{
    display: inline-flex; align-items: center; justify-content: center;
    padding: 9px 16px; border-radius: 10px; cursor: pointer;
    font-size: 12.5px; font-weight: 600; letter-spacing: 0.4px;
    white-space: nowrap; text-decoration: none;
    transition: background 0.2s, box-shadow 0.2s, transform 0.15s;
    line-height: 1; color: #0D1B17; font-family: inherit;
  }}
  .abtn-print {{
    background: #F2F7F5;
    border: 1px solid rgba(0,229,160,0.50);
    box-shadow: 0 0 14px rgba(0,229,160,0.12);
  }}
  .abtn-print:hover {{
    background: rgba(0,229,160,0.20);
    border-color: rgba(0,229,160,0.80);
    box-shadow: 0 0 20px rgba(0,229,160,0.28);
    transform: translateY(-1px);
  }}
  .abtn-save {{
    background: rgba(0,229,160,0.22);
    border: 1px solid rgba(0,229,160,0.55);
    box-shadow: 0 0 14px rgba(0,229,160,0.18);
  }}
  .abtn-save:hover {{
    background: rgba(0,229,160,0.35);
    border-color: #0D1B17;
    box-shadow: 0 0 24px rgba(0,229,160,0.38);
    transform: translateY(-1px);
  }}
  .abtn:active {{ transform: translateY(0); }}
</style>
</head>
<body>
<div class="action-btns">
  {pdf_button}
  <a class="abtn abtn-save" href="{save_href}" download="historico_defeitos_fornecedor.xlsx">
    Salvar por Fornecedor
  </a>
  <button class="abtn abtn-save" onclick="openRange()">Filtrar por Faixa</button>
</div>
{script_html}
<script>
  function openRange() {{
    try {{
      const btn = window.parent.document.querySelector('.st-key-hist_range_toggle button');
      if (btn) {{ btn.click(); }}
    }} catch (err) {{ console.error('openRange falhou:', err); }}
  }}
</script>
</body>
</html>""",
        height=44,
    )

    # O botão "Filtrar por Faixa" fica DENTRO do iframe acima, na mesma linha do
    # "Salvar por Fornecedor" e com o mesmo estilo. Como um botão no iframe não
    # dispara rerun do Streamlit sozinho, ele "clica" (via JS) neste botão nativo
    # OCULTO — que, ao retornar True no rerun, ABRE o popup (st.dialog) com o
    # histórico COMPLETO. O Streamlit mantém o diálogo aberto nas interações
    # seguintes e o fecha sozinho no "X"; não recarregamos a página (um reload
    # reiniciaria a sessão e deslogaria o usuário).
    st.markdown(
        "<style>.st-key-hist_range_toggle{display:none;}</style>",
        unsafe_allow_html=True,
    )
    if st.button("toggle_range", key="hist_range_toggle"):
        _render_supplier_range_dialog(full_df if full_df is not None else filtered)

    if sem_filtro:
        st.caption(
            f"⚠️ Sem filtro aplicado: os {len(filtered):,} registros serão exportados "
            "**apenas em Excel**. Filtre por oficina ou período para habilitar a prévia em PDF."
        )
    elif html_page is None:
        st.caption(
            f"✦ {len(filtered):,} registro(s) filtrado(s). "
            "A prévia em PDF está indisponível no momento — o Excel continua funcionando."
        )
    else:
        st.caption(f"✦ {len(filtered):,} registro(s) filtrado(s), agrupados por fornecedor.")


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
# Popup: filtro de fornecedores por faixa
# ══════════════════════════════════════════════════════════════════════════════

#: Rótulo exibido → chave de métrica de DataProcessor.supplier_summary_in_range.
_RANGE_METRICS = {
    "Total de Remontes": "remonte",
    "Total de Ordens":   "ordens",
    "Total em Valor (R$)": "valor",
}


@st.dialog("🎯 Fornecedores por Faixa", width="large")
def _render_supplier_range_dialog(df: pd.DataFrame) -> None:
    """Popup (janela) para filtrar fornecedores por faixa de uma métrica.

    O usuário escolhe a métrica (total de remontes, de ordens ou em valor) e o
    intervalo [De, Até]. São listados — agrupados por fornecedor — todos os
    fornecedores de TODO o histórico cujo total cai na faixa, com as colunas
    Fornecedor · Total de Remontes · Total de Ordens · Total em Valor e um botão
    de exportação em PDF.

    Fronteira defensiva: qualquer falha degrada apenas o popup, com aviso
    amigável — nunca derruba a página.
    """
    st.markdown(
        f"<p style='font-size:12.5px;color:{COLORS['text_muted']};margin:0 0 12px;line-height:1.6'>"
        "Escolha a métrica e o intervalo. São listados os fornecedores de "
        "<strong>todo o histórico</strong> cujo total cai dentro da faixa, "
        "agrupados por fornecedor.</p>",
        unsafe_allow_html=True,
    )

    try:
        processor = DataProcessor(df)
        summary_all = processor.supplier_summary()
    except Exception:  # noqa: BLE001 — fronteira defensiva local
        logger.exception("Falha ao agregar fornecedores para o filtro por faixa")
        st.warning(
            "⚠️ Não foi possível carregar os fornecedores agora. "
            "Tente novamente em instantes."
        )
        return

    if summary_all.empty:
        st.info("Nenhum fornecedor no histórico ainda.")
        return

    metric_label = st.selectbox(
        "Filtrar por", list(_RANGE_METRICS), key="hist_range_metric"
    )
    metric = _RANGE_METRICS[metric_label]
    metric_col = DataProcessor.SUPPLIER_SUMMARY_METRICS[metric]
    is_valor = metric == "valor"

    serie = summary_all[metric_col]
    data_min, data_max = float(serie.min()), float(serie.max())

    col_lo, col_hi = st.columns(2)
    with col_lo:
        if is_valor:
            low = st.number_input(
                "De (R$)", value=data_min, step=100.0, format="%.2f",
                key=f"hist_range_low_{metric}",
            )
        else:
            low = st.number_input(
                "De", value=int(data_min), step=1,
                key=f"hist_range_low_{metric}",
            )
    with col_hi:
        if is_valor:
            high = st.number_input(
                "Até (R$)", value=data_max, step=100.0, format="%.2f",
                key=f"hist_range_high_{metric}",
            )
        else:
            high = st.number_input(
                "Até", value=int(data_max), step=1,
                key=f"hist_range_high_{metric}",
            )

    try:
        result = processor.supplier_summary_in_range(metric, float(low), float(high))
    except Exception:  # noqa: BLE001 — fronteira defensiva local
        logger.exception("Falha ao filtrar fornecedores por faixa")
        st.warning("⚠️ Não foi possível aplicar o filtro agora.")
        return

    _spacer(6)
    if result.empty:
        st.info("Nenhum fornecedor encontrado nesta faixa. Ajuste os limites acima.")
        return

    st.markdown(
        f"<p style='font-size:12px;color:{COLORS['text_muted']};margin:0 0 6px'>"
        f"✦ {len(result):,} fornecedor(es) na faixa selecionada.</p>",
        unsafe_allow_html=True,
    )
    _render_supplier_summary_table(result)

    _spacer(8)
    _render_range_pdf_button(result, metric_label, float(low), float(high), is_valor)


def _render_supplier_summary_table(summary: pd.DataFrame) -> None:
    """Tabela agrupada por fornecedor no MESMO padrão visual das demais do app
    (reutiliza _wrap_table / _td / _row_bg / _VAR_TH)."""
    headers = [
        (_VAR_TH_L + "width:34%;", "Fornecedor"),
        (_VAR_TH + "width:16%;", "Total de Remontes"),
        (_VAR_TH + "width:15%;", "Quantidade"),
        (_VAR_TH + "width:15%;", "Total de Ordens"),
        (_VAR_TH + "width:20%;", "Total em Valor"),
    ]
    head_html = "".join(f'<th style="{style}">✦ {name}</th>' for style, name in headers)

    rows_html = ""
    for i, (_, row) in enumerate(summary.iterrows()):
        bg = _row_bg(i)
        rows_html += "<tr>" + (
            _td(f'<strong>{row["fornecedor"]}</strong>', bg, "left")
            + _td(f'{int(row["total_remonte"]):,}', bg, "center")
            + _td(f'{int(row["total_quantidade"]):,}', bg, "center")
            + _td(f'{int(row["total_ordens"]):,}', bg, "center")
            + _td(f'R$ {float(row["total_valor"]):,.2f}', bg, "center")
        ) + "</tr>"

    st.markdown(_wrap_table(head_html, rows_html, max_height="420px"), unsafe_allow_html=True)


def _render_range_pdf_button(
    summary: pd.DataFrame, metric_label: str, low: float, high: float, is_valor: bool
) -> None:
    """Botão que abre a prévia em PDF do resultado da faixa numa nova aba.

    Reaproveita o mesmo mecanismo de prévia da barra de exportação (data-URI +
    window.open). Fronteira defensiva: se a geração falhar, apenas informa —
    a tabela na tela continua válida."""
    try:
        html_page = _generate_fornecedores_faixa_html(
            summary, metric_label, low, high, is_valor
        )
    except Exception:  # noqa: BLE001 — fronteira defensiva local
        logger.exception("Falha ao gerar o PDF do filtro por faixa")
        st.caption("A exportação em PDF está indisponível no momento.")
        return

    html_b64 = base64.b64encode(html_page.encode("utf-8")).decode()
    components.html(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: transparent; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
  .abtn {{
    display: inline-flex; align-items: center; justify-content: center;
    padding: 9px 16px; border-radius: 10px; cursor: pointer;
    font-size: 12.5px; font-weight: 600; letter-spacing: 0.4px;
    white-space: nowrap; text-decoration: none; line-height: 1;
    color: #0D1B17; font-family: inherit;
    background: rgba(0,229,160,0.22);
    border: 1px solid rgba(0,229,160,0.55);
    box-shadow: 0 0 14px rgba(0,229,160,0.18);
    transition: background 0.2s, box-shadow 0.2s, transform 0.15s;
  }}
  .abtn:hover {{
    background: rgba(0,229,160,0.35); border-color: #0D1B17;
    box-shadow: 0 0 24px rgba(0,229,160,0.38); transform: translateY(-1px);
  }}
  .abtn:active {{ transform: translateY(0); }}
</style>
</head>
<body>
<button class="abtn" onclick="openPreview()">📄 Exportar / Imprimir PDF</button>
<script>
  const _HTML_B64 = "{html_b64}";
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
      console.error("Erro ao abrir prévia:", err);
      alert("Não foi possível abrir a prévia. Permita popups para este site.");
    }}
  }}
</script>
</body>
</html>""",
        height=48,
    )


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
