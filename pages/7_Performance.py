# -*- coding: utf-8 -*-
"""
Página: Performance de Fornecedores.

Responde uma pergunta que o dashboard de defeitos não responde: quanto de cada
ordem chegou boa. Para isso a base é consolidada por ORDEM MESTRE, contando o
REAL CORTADO uma única vez — ver `src/performance/domain/calculations.py`.

Duas bases, escolhidas na tela
─────────────────────────────
O app tem duas tabelas de defeitos com schema IDÊNTICO e significados diferentes.
O seletor "Base de análise" expõe as duas (ver `src/performance/config.py`):

  • **Completa** (`historico_defeitos`) — padrão. Registro permanente e imutável
    de tudo o que foi importado. É a única base em que "performance do fornecedor
    no período" quer dizer o que o nome diz.

  • **Atual** (`registros_defeitos`) — a base ativa, a mesma do dashboard.
    Responde "o que está em aberto agora".

A armadilha, e o motivo de o padrão ser Completa: `src/data/cobranca_history.py`
executa `DELETE FROM registros_defeitos` quando uma cobrança é emitida. A base
Atual ENCOLHE, e encolhe justamente pelos piores fornecedores — que são os
cobrados. Analisar tendência sobre ela faz a performance subir sozinha com o
tempo e um fornecedor recém-cobrado parecer recuperado sem ter mudado nada. Por
isso a página exibe um aviso sempre que a base Atual está selecionada, e carimba
a base escolhida no cabeçalho e em todos os relatórios exportados.

Custo de banco: ZERO consultas próprias
───────────────────────────────────────
A página não escreve SQL. Cada base é lida pela função cacheada que já serve a
página dona dela — `load_historico()` (Histórico) e `load_data_from_disk()`
(Dashboard), ambas `@st.cache_data` com TTL de 60s e sem argumentos. Trocar de
base no seletor não gera consulta nova se aquela tabela já foi lida neste
processo; e alternar de ida e volta reusa as duas entradas de cache.

A tentação seria escrever aqui um `SELECT` só com as 8 colunas que a análise usa.
Seria PIOR: um segundo padrão de consulta é um segundo scan da tabela e uma
segunda entrada de cache, dobrando o trabalho do Postgres em vez de reduzi-lo.
Se a leitura precisar ficar mais barata, o lugar são os módulos de dados, que
servem todas as páginas de uma vez.

Depois da leitura, tudo é em memória: a consolidação é cacheada por impressão
digital do conteúdo (ver `base_fingerprint`) e os filtros, sliders e abas
trabalham sobre o DataFrame já carregado, sem voltar ao banco.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date

import pandas as pd
import streamlit as st

from src.auth.session import require_login
from src.data.database import DatabaseUnavailableError
from src.data.historico_defeitos import load_historico
from src.data.loader import load_data_from_disk
from src.performance.config import (
    BASES, DEFAULT_BASE, DEFAULT_LOSS_THRESHOLD, DEFAULT_TARGET, BaseOption,
)
from src.performance.data.dataset_builder import base_fingerprint, build_dataset
from src.performance.domain.exceptions import PerformanceError
from src.performance.presentation.components import (
    defects_chart, html_table, metric_card, panel_title, pdf_preview,
    printable_report_preview, rank_card, render_chart, status_donut,
    supplier_chart, trend_chart,
)
from src.performance.presentation.formatters import currency_br, number_br, percent_br
from src.performance.presentation.theme import apply_performance_theme
from src.performance.services.analytics_service import AnalyticsService
from src.performance.services.report_service import PdfReportService, SupplierExportService
from src.ui.error_boundary import page_guard, render_db_error

logger = logging.getLogger(__name__)


# ── Fronteiras de erro por seção ──────────────────────────────────────────────
# `page_guard` protege a página inteira, mas só contra `DatabaseUnavailableError`
# — de propósito, ver o docstring de `src/ui/error_boundary.py`. Só que a partir
# do dataset construído esta página não fala mais com o banco: o que pode falhar
# aqui é a MONTAGEM de um relatório, e `report_service` converte qualquer falha
# interna em `ReportGenerationError`. Sem uma fronteira própria, esse erro sobe
# até o topo e leva junto tudo o que ainda não tinha sido desenhado — as abas são
# executadas em sequência, então uma falha na aba de Fornecedores apaga também as
# de Ordens críticas e Qualidade dos dados, e o usuário recebe um traceback cru.
#
# `except Exception` aqui é seguro para o control-flow do Streamlit: `st.stop()` e
# `st.rerun()` levantam `ScriptControlException`, que herda de `BaseException` e
# não de `Exception` — portanto passa direto por estas fronteiras.


@contextmanager
def _section(name: str):
    """Isola uma seção: o que falhar aqui não derruba o resto da página."""
    try:
        yield
    except DatabaseUnavailableError as exc:
        render_db_error(exc)
    except Exception:  # noqa: BLE001 — fronteira: nada de traceback cru na UI
        logger.exception("Falha ao renderizar a seção '%s' da página de Performance", name)
        st.warning(
            f"⚠️ Não foi possível exibir **{name}** agora. "
            "As demais seções da página continuam disponíveis."
        )


def _report_bytes(builder, *args, what: str) -> bytes | None:
    """Monta um arquivo para download. Devolve None (com aviso) se a montagem falhar.

    O `st.download_button` recebe os BYTES como argumento, então o arquivo é
    montado durante o render — antes e independentemente de qualquer clique. Uma
    falha aqui, sem esta proteção, derrubaria a aba inteira de quem só queria ver
    a tabela na tela.
    """
    try:
        return builder(*args)
    except Exception:  # noqa: BLE001 — fronteira: nada de traceback cru na UI
        logger.exception("Falha ao gerar %s na página de Performance", what)
        st.warning(
            f"⚠️ Não foi possível gerar {what} para os filtros atuais. "
            "Reduza o recorte ou tente novamente; o restante da página continua válido."
        )
        return None


# ── Carga ─────────────────────────────────────────────────────────────────────

def _base_selector() -> BaseOption:
    """Seletor da base analisada. Retorna a opção escolhida."""
    st.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:var(--ag-text-muted);margin:0 0 6px">🗄️ Base de análise</p>',
        unsafe_allow_html=True,
    )
    keys = list(BASES)
    chosen = st.segmented_control(
        "Base de análise",
        options=keys,
        format_func=lambda key: BASES[key].label,
        default=DEFAULT_BASE,
        key="perf_base",
        label_visibility="collapsed",
    )
    # `st.segmented_control` devolve None se o usuário desmarcar a opção ativa.
    option = BASES[chosen or DEFAULT_BASE]
    st.caption(option.caption)
    if option.warning:
        st.warning(option.warning)
    return option


def _load_frame(option: BaseOption) -> pd.DataFrame | None:
    """Lê a base escolhida pela função cacheada que já serve a página dona dela.

    Nenhuma das duas usa `st.session_state["df"]`: aquela chave é do dashboard e
    guarda só a base ativa, o que impediria a opção Completa.
    """
    if option.key == "atual":
        return load_data_from_disk()
    return load_historico()


@st.cache_data(show_spinner=False)
def _load_dataset(_df: pd.DataFrame, fingerprint: str, base_key: str):
    """Consolida a base em ordens. `_df` não é hasheado (prefixo `_`).

    A identidade do cache é (`fingerprint`, `base_key`); o DataFrame entra apenas
    como dado. `base_key` participa da chave para que alternar entre Completa e
    Atual não sirva o dataset de uma como se fosse da outra — mesmo que as duas
    tivessem, por acaso, exatamente o mesmo conteúdo.
    """
    option = BASES[base_key]
    return build_dataset(_df, source_name=option.source_name, table_name=option.table)


@st.cache_data(show_spinner=False)
def _build_orders_pdf(critical, summary, target, threshold, period) -> bytes:
    return PdfReportService.build(critical, summary, target, threshold, period)


@st.cache_data(show_spinner=False)
def _build_ranking_excel(summary, target, period) -> bytes:
    return SupplierExportService.build_excel(summary, target, period)


@st.cache_data(show_spinner=False)
def _build_ranking_pdf(summary, target, period) -> bytes:
    return SupplierExportService.build_pdf(summary, target, period)


# ── Cabeçalho e filtros ───────────────────────────────────────────────────────

def _header(period: str, orders: int, option: BaseOption) -> None:
    # O total é formatado por number_br, não por `{:,}` + replace: um replace de
    # vírgula no HTML inteiro também atingiria os rgba() do estilo abaixo.
    total = number_br(orders)
    # A base fica carimbada no cabeçalho: sem isso, uma tela da base Atual é
    # indistinguível de uma da Completa, e as duas contam histórias diferentes.
    chip = (
        ("rgba(226,75,74,0.14)", "rgba(226,75,74,0.32)")
        if option.warning
        else ("rgba(0,229,160,0.18)", "rgba(0,229,160,0.3)")
    )
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(0,0,0,0.06);
                    margin-bottom:1.2rem">
            <div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">
                <span style="font-size:26px;font-weight:700;color:var(--ag-text-primary)">
                    Performance de Fornecedores</span>
                <span style="font-size:12px;color:var(--ag-text-subtle);
                             background:{chip[0]};padding:3px 10px;border-radius:20px;
                             border:1px solid {chip[1]}">
                    Base {option.label}
                </span>
                <span style="font-size:12px;color:var(--ag-text-subtle);
                             background:rgba(0,229,160,0.18);padding:3px 10px;border-radius:20px;
                             border:1px solid rgba(0,229,160,0.3)">
                    {total} ordens consolidadas
                </span>
            </div>
            <p style="color:var(--ag-text-muted);font-size:13px;margin:5px 0 0">
                Perdas, remontes e aderência à meta, consolidados por Ordem Mestre ·
                Período: {period} · Origem: {option.table}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _filter_controls(dataset, option: BaseOption):
    """Barra de filtros da página. Tudo aplicado em memória.

    As chaves de fornecedor/mês/semana/data levam o sufixo da base porque o
    Streamlit guarda o valor do widget pela chave: um fornecedor escolhido na
    base Completa pode não existir na Atual, e o `st.multiselect` levanta exceção
    quando o valor guardado não está entre as opções (o mesmo vale para uma data
    fora do novo intervalo). Sufixar dá a cada base o seu próprio estado de
    filtro. Meta e corte de perda são percentuais, valem para as duas, e por isso
    continuam com chave única.
    """
    orders = dataset.orders
    scope = option.key
    st.markdown(
        '<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        'color:var(--ag-text-muted);margin:0 0 8px">Filtros e parâmetros</p>',
        unsafe_allow_html=True,
    )

    with st.container(key="perf_filters"):
        col_params, col_suppliers, col_period = st.columns(3)

        with col_params, st.popover("Parâmetros", use_container_width=True):
            target_pct = st.slider(
                "Meta de performance (%)", 50, 100, int(DEFAULT_TARGET * 100), 1,
                key="perf_target",
                help="Abaixo desta performance o fornecedor é marcado como fora da meta.",
            )
            loss_pct = st.slider(
                "Corte de perda por ordem (%)", 0, 100, int(DEFAULT_LOSS_THRESHOLD * 100), 1,
                key="perf_threshold",
                help="Ordens com perda igual ou maior entram no recorte de ordens críticas.",
            )

        with col_suppliers, st.popover("Fornecedores", use_container_width=True):
            suppliers = st.multiselect(
                "Fornecedor",
                options=sorted(orders["supplier"].dropna().unique().tolist()),
                placeholder="Todos os fornecedores",
                key=f"perf_suppliers_{scope}",
            )

        min_date = orders["production_date"].min().date()
        max_date = orders["production_date"].max().date()
        with col_period, st.popover("Período", use_container_width=True):
            selected_dates = st.date_input(
                "Data de produção",
                value=(min_date, max_date),
                min_value=min_date, max_value=max_date,
                format="DD/MM/YYYY", key=f"perf_dates_{scope}",
            )
            months = st.multiselect(
                "Mês",
                options=sorted(orders["month"].dropna().unique().tolist(), reverse=True),
                placeholder="Todos os meses", key=f"perf_months_{scope}",
            )
            weeks = st.multiselect(
                "Semana ISO",
                options=sorted(orders["week"].dropna().unique().tolist(), reverse=True),
                placeholder="Todas as semanas", key=f"perf_weeks_{scope}",
            )

    if isinstance(selected_dates, (tuple, list)) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    elif isinstance(selected_dates, date):
        start_date = end_date = selected_dates
    else:
        start_date, end_date = min_date, max_date

    return target_pct / 100, loss_pct / 100, suppliers, start_date, end_date, weeks, months


def _period_text(orders: pd.DataFrame) -> str:
    if orders.empty:
        return "sem dados"
    start = orders["production_date"].min().strftime("%d/%m/%Y")
    end = orders["production_date"].max().strftime("%d/%m/%Y")
    return start if start == end else f"{start} a {end}"


# ── Abas ──────────────────────────────────────────────────────────────────────

SUPPLIER_COLUMNS = [
    ("supplier", "Fornecedor", "text"),
    ("orders", "Ordens", "number"),
    ("real_cut", "Real cortado", "number"),
    ("defect_pieces", "Defeitos", "number"),
    ("defect_rate", "% defeito", "percent"),
    ("performance", "Performance", "percent"),
    ("minutes_generated", "Minutos", "minutes"),
    ("defect_cost", "Custo das perdas", "currency"),
]

ORDER_COLUMNS = [
    ("supplier", "Fornecedor", "text"),
    ("master_order", "Ordem mestre", "text"),
    ("production_period", "Data de produção", "text"),
    ("real_cut", "Real cortado", "number"),
    ("defect_pieces", "Perdas", "number"),
    ("defect_rate", "% perda", "percent"),
    ("performance", "Performance", "percent"),
    ("minutes_generated", "Minutos", "minutes"),
    ("defect_cost", "Custo", "currency"),
    ("defect_types", "Tipos de remonte", "text"),
]


def _overview_tab(filtered, summary: pd.DataFrame, target: float) -> None:
    metrics = AnalyticsService.metrics(filtered.orders, target)

    cards = st.columns(5)
    with cards[0]:
        metric_card(
            "Performance geral", percent_br(metrics.performance),
            f"Meta definida em {target:.0%}",
            "danger" if metrics.performance < target else "cyan",
        )
    with cards[1]:
        metric_card("Real cortado", number_br(metrics.real_cut), "peças produzidas", "cyan")
    with cards[2]:
        metric_card(
            "Peças com defeito", number_br(metrics.defect_pieces),
            f"{percent_br(metrics.defect_rate)} do real cortado", "danger",
        )
    with cards[3]:
        metric_card(
            "Abaixo da meta", str(metrics.suppliers_below_target),
            f"de {metrics.suppliers} fornecedores analisados",
            "danger" if metrics.suppliers_below_target else "cyan",
        )
    with cards[4]:
        metric_card(
            "Custo das perdas", currency_br(metrics.defect_cost),
            f"{number_br(metrics.minutes_generated, 1)} minutos em {metrics.orders} ordens",
            "danger",
        )

    panel_title("Extremos de qualidade")
    ranks = st.columns(2)
    with ranks[0]:
        rank_card("Maior índice de defeitos", metrics.worst_supplier,
                  metrics.worst_supplier_rate, "bad")
    with ranks[1]:
        rank_card("Menor índice de defeitos", metrics.best_supplier,
                  metrics.best_supplier_rate, "good")

    render_chart(supplier_chart(summary, target), 460, "perf-supplier-chart")

    lower = st.columns([1, 1.65])
    with lower[0]:
        render_chart(status_donut(summary, target), 390, "perf-status-donut")
    with lower[1]:
        defects = AnalyticsService.defect_breakdown(filtered.rows, 10)
        render_chart(defects_chart(defects), 390, "perf-defect-types")

    panel_title("Evolução no tempo")
    frequency = st.radio(
        "Agrupar por", options=["Mês", "Semana"], horizontal=True,
        key="perf_trend_frequency", label_visibility="collapsed",
    )
    trend = AnalyticsService.performance_trend(
        filtered.orders, "week" if frequency == "Semana" else "month"
    )
    label = "semana ISO" if frequency == "Semana" else "mês"
    render_chart(trend_chart(trend, target, label), 380, "perf-trend")


def _suppliers_tab(summary: pd.DataFrame, target: float, period: str) -> None:
    panel_title("Ranking de fornecedores")
    if summary.empty:
        st.info("Nenhum fornecedor encontrado para os filtros atuais.")
        return

    worst, best = st.columns(2)
    with worst:
        st.markdown("#### Maiores perdas")
        html_table(summary.head(10), SUPPLIER_COLUMNS, target)
    with best:
        st.markdown("#### Melhores performances")
        html_table(
            summary.sort_values("performance", ascending=False).head(10),
            SUPPLIER_COLUMNS, target,
        )

    st.markdown("#### Dados agregados por fornecedor")
    html_table(summary, SUPPLIER_COLUMNS, target)

    with st.container(key="perf_export"):
        st.markdown(
            '<div class="perf-export-heading"><strong>Exportar ranking</strong>'
            "<span>Escolha o formato do relatório consolidado.</span></div>",
            unsafe_allow_html=True,
        )
        format_column, button_column = st.columns([1.15, 1], vertical_alignment="bottom")
        with format_column:
            export_format = st.selectbox(
                "Formato do arquivo", options=["Excel (.xlsx)", "PDF (.pdf)"],
                key="perf_export_format",
            )
        with button_column:
            if export_format == "Excel (.xlsx)":
                payload = _report_bytes(
                    _build_ranking_excel, summary, target, period,
                    what="o Excel do ranking",
                )
                if payload is not None:
                    st.download_button(
                        "Baixar ranking em Excel",
                        payload,
                        "ranking_fornecedores.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
            else:
                payload = _report_bytes(
                    _build_ranking_pdf, summary, target, period,
                    what="o PDF do ranking",
                )
                if payload is not None:
                    st.download_button(
                        "Baixar ranking em PDF",
                        payload,
                        "ranking_fornecedores.pdf",
                        "application/pdf",
                        use_container_width=True,
                    )


def _orders_tab(filtered, summary: pd.DataFrame, target: float,
                threshold: float, period: str) -> None:
    critical = AnalyticsService.critical_orders(filtered.orders, threshold)

    metrics = st.columns(4)
    with metrics[0]:
        metric_card("Ordens críticas", number_br(len(critical)),
                    f"perda a partir de {threshold:.0%}", "danger")
    with metrics[1]:
        metric_card("Fornecedores envolvidos", number_br(critical["supplier"].nunique()),
                    "no recorte crítico", "danger")
    with metrics[2]:
        metric_card("Perdas críticas", number_br(critical["defect_pieces"].sum()),
                    "peças com defeito", "danger")
    with metrics[3]:
        metric_card("Custo crítico", currency_br(critical["defect_cost"].sum()),
                    f"{number_br(critical['minutes_generated'].sum(), 1)} minutos gerados",
                    "danger")

    st.markdown("#### Detalhamento por Ordem Mestre")
    html_table(critical, ORDER_COLUMNS, target)

    st.markdown("#### Relatório para impressão")
    st.caption("O relatório respeita todos os filtros e o corte de perda selecionado.")
    pdf = _report_bytes(
        _build_orders_pdf, critical, summary, target, threshold, period,
        what="o PDF do relatório de ordens críticas",
    )
    if pdf is not None:
        st.download_button(
            "Baixar relatório em PDF", pdf,
            "relatorio_performance_fornecedores.pdf", "application/pdf",
        )
    with st.expander("Pré-visualizar relatório para impressão", expanded=False):
        # A prévia em HTML não depende do PDF: ela continua disponível mesmo
        # quando a montagem do arquivo falhou, e é justamente aí que ela serve.
        with _section("a pré-visualização do relatório"):
            printable_report_preview(critical, summary, target, threshold, period)
        if pdf is not None:
            st.caption("Visualização do arquivo PDF gerado")
            with _section("a visualização do PDF"):
                pdf_preview(pdf, height=520)


def _quality_tab(dataset) -> None:
    report = dataset.quality
    panel_title("Diagnóstico da leitura da base")

    cols = st.columns(4)
    with cols[0]:
        metric_card("Linhas na base", number_br(report.source_rows), report.sheet_name)
    with cols[1]:
        metric_card("Linhas válidas", number_br(report.valid_rows), "usadas na análise")
    with cols[2]:
        metric_card("Ordens consolidadas", number_br(report.order_rows),
                    "sem duplicar o real cortado")
    with cols[3]:
        metric_card("Linhas descartadas", number_br(report.discarded_rows), "por validação",
                    "danger" if report.discarded_rows else "cyan")

    mapping = dataset.column_map
    st.markdown("#### Colunas identificadas")
    mapping_frame = pd.DataFrame(
        [
            ["Data de produção", mapping.production_date],
            ["Ordem mestre", mapping.master_order],
            ["Fornecedor", mapping.supplier],
            ["Quantidade perdida", mapping.defect_quantity],
            ["Real cortado", mapping.real_cut],
            ["Minutos gerados", mapping.minutes or "Não disponível"],
            ["Tipo de defeito", mapping.defect_type or "Não disponível"],
            ["Custo do processo", mapping.cost or "Não disponível"],
        ],
        columns=["Campo da análise", "Coluna da base"],
    )
    html_table(
        mapping_frame,
        [("Campo da análise", "Campo da análise", "text"),
         ("Coluna da base", "Coluna da base", "text")],
    )

    st.markdown("#### Alertas de qualidade")
    if report.warnings:
        for warning in report.warnings:
            st.markdown(
                f"<div class='perf-note'>{warning}</div><div style='height:8px'></div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("Nenhum alerta relevante foi encontrado na leitura da base.")


# ── Main ──────────────────────────────────────────────────────────────────────

@page_guard
def main() -> None:
    require_login()
    apply_performance_theme()

    option = _base_selector()
    df = _load_frame(option)
    if df is None or df.empty:
        origem = (
            "Importe os dados em <strong>Histórico</strong>."
            if option.key == "completa"
            else "Faça a carga da base ativa em <strong>Análise de defeitos</strong>."
        )
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;
                        justify-content:center;min-height:38vh;text-align:center;gap:10px">
                <div style="font-size:36px;opacity:0.18">📈</div>
                <p style="font-size:15px;font-weight:600;color:var(--ag-text-primary);margin:0">
                    A base {option.label} está vazia</p>
                <p style="font-size:13px;color:var(--ag-text-subtle);margin:0;max-width:360px;
                          line-height:1.6">
                    Nada encontrado em <code>{option.table}</code>. {origem}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    try:
        dataset = _load_dataset(df, base_fingerprint(df), option.key)
    except PerformanceError as exc:
        st.error(f"⚠️ {exc}")
        return

    target, threshold, suppliers, start_date, end_date, weeks, months = _filter_controls(dataset, option)
    filtered = AnalyticsService.filter_dataset(
        dataset, suppliers, start_date, end_date, weeks, months
    )
    summary = AnalyticsService.supplier_summary(filtered.orders, target)
    period = _period_text(filtered.orders)
    # A base entra no rótulo do período para viajar junto com todo PDF/Excel
    # exportado: um ranking impresso da base Atual, sem essa marca, seria lido
    # como performance do parceiro.
    report_period = f"{period} · Base {option.label}"

    _header(period, len(filtered.orders), option)

    if filtered.orders.empty:
        st.warning(
            "⚠️ Os filtros atuais não retornaram ordens. "
            "Ajuste o período ou remova algum filtro."
        )
        return

    tabs = st.tabs(
        ["Visão geral", "Fornecedores", "Ordens críticas e PDF", "Qualidade dos dados"]
    )
    # Cada aba tem a sua própria fronteira: o corpo de TODAS elas é executado a
    # cada rerun (o `with` é Python puro; o Streamlit só esconde as inativas no
    # navegador), então sem isso a falha de uma aba apagaria as outras três.
    with tabs[0], _section("a Visão geral"):
        _overview_tab(filtered, summary, target)
    with tabs[1], _section("o ranking de Fornecedores"):
        _suppliers_tab(summary, target, report_period)
    with tabs[2], _section("as Ordens críticas"):
        _orders_tab(filtered, summary, target, threshold, report_period)
    with tabs[3], _section("a Qualidade dos dados"):
        _quality_tab(dataset)


main()
