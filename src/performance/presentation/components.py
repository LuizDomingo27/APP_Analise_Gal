# -*- coding: utf-8 -*-
"""
Componentes visuais da página de Performance.

Os gráficos são renderizados por `src.charts.render.echart` — o mesmo caminho do
dashboard principal (streamlit-echarts). O app original carregava o ECharts de
uma CDN dentro de um `components.html`; aqui isso seria um retrocesso: colocaria
a página refém de acesso externo e a deixaria fora dos tokens de tema. As specs
já eram dicts puros, então a troca é só no ponto de render.
"""

from __future__ import annotations

import base64
import html

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.charts.render import echart
from src.performance.config import COLORS
from src.performance.presentation.formatters import (
    currency_br, date_br, number_br, percent_br,
)


# ── Cartões ───────────────────────────────────────────────────────────────────


def render_html(markup: str, height: int, scrolling: bool = False) -> None:
    """Embute markup gerado num iframe isolado.

    Prefere `st.iframe`; `st.components.v1.html` está deprecado e marcado para
    remoção, mas ainda é a única opção nas versões antigas de Streamlit que
    suportamos.
    """
    iframe = getattr(st, "iframe", None)
    if iframe is not None:
        iframe(markup, height=height)
        return
    components.html(markup, height=height, scrolling=scrolling)

def metric_card(label: str, value: str, detail: str, tone: str = "cyan") -> None:
    safe_tone = "danger" if tone == "danger" else "cyan"
    st.markdown(
        f"""<div class="perf-kpi {'danger' if tone == 'danger' else ''}">
        <div class="perf-kpi-label">{html.escape(label)}</div>
        <div class="perf-kpi-value {safe_tone}">{html.escape(value)}</div>
        <div class="perf-kpi-detail">{html.escape(detail)}</div></div>""",
        unsafe_allow_html=True,
    )


def rank_card(label: str, supplier: str, rate: float, status: str) -> None:
    bad = status == "bad"
    st.markdown(
        f"""<div class="perf-rank"><div class="perf-kpi-label">{html.escape(label)}</div>
        <div class="perf-rank-name">{html.escape(supplier)}</div>
        <span class="perf-badge {'bad' if bad else 'good'}">
        {percent_br(rate)} de defeitos</span></div>""",
        unsafe_allow_html=True,
    )


def panel_title(text: str) -> None:
    st.markdown(f"<div class='perf-panel-title'>{html.escape(text)}</div>", unsafe_allow_html=True)


# ── Gráficos ──────────────────────────────────────────────────────────────────

def _base_option() -> dict:
    return {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": "Inter, sans-serif", "color": COLORS["muted"]},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": COLORS["surface"],
            "borderColor": COLORS["border"],
            "textStyle": {"color": COLORS["text"]},
        },
        "grid": {"left": 22, "right": 22, "top": 42, "bottom": 28, "containLabel": True},
    }


def supplier_chart(summary: pd.DataFrame, target: float) -> dict:
    """Barras de performance dos 15 piores fornecedores, com a linha da meta."""
    view = summary.sort_values("performance").head(15)
    minimum = (
        max(0, min(75, int(float(view["performance"].min()) * 100) - 3))
        if not view.empty else 0
    )
    option = _base_option()
    option.update({
        "grid": {"left": 54, "right": 24, "top": 72, "bottom": 112},
        "title": {
            "text": "Performance por fornecedor",
            "subtext": "15 menores índices no recorte",
            "textStyle": {"color": COLORS["cyan_dark"], "fontSize": 13},
            "subtextStyle": {"color": COLORS["muted"]},
        },
        "xAxis": {
            "type": "category",
            "data": view["supplier"].tolist(),
            "axisLabel": {
                "color": COLORS["muted"], "interval": 0, "rotate": 40,
                "width": 92, "overflow": "truncate",
            },
            "axisLine": {"show": False},
            "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "value", "min": minimum, "max": 100,
            "axisLabel": {"formatter": "{value}%", "color": COLORS["muted"]},
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "splitLine": {"show": False},
        },
        "series": [{
            "type": "bar",
            "barMaxWidth": 30,
            "data": [
                {
                    "value": round(float(value) * 100, 2),
                    "itemStyle": {
                        "color": COLORS["danger"] if value < target else COLORS["cyan"],
                        "borderRadius": [7, 7, 0, 0],
                    },
                }
                for value in view["performance"]
            ],
            "label": {
                "show": True, "position": "top", "distance": 6, "formatter": "{c}%",
                "color": COLORS["text"], "fontSize": 10, "fontWeight": 800,
                "backgroundColor": COLORS["surface"], "borderColor": COLORS["border"],
                "borderWidth": 1, "borderRadius": 5, "padding": [3, 4],
            },
            "markLine": {
                "silent": True, "symbol": "none",
                "data": [{"yAxis": target * 100}],
                "lineStyle": {"color": COLORS["amber"], "type": "dashed"},
                "label": {
                    "formatter": f"Meta {target:.0%}",
                    "color": COLORS["amber"], "position": "insideEndTop",
                },
            },
        }],
    })
    return option


def status_donut(summary: pd.DataFrame, target: float) -> dict:
    below = int(summary["performance"].lt(target).sum()) if not summary.empty else 0
    within = int(len(summary) - below)
    return {
        "backgroundColor": "transparent",
        "title": {
            "text": "Aderência à meta", "subtext": "Fornecedores no recorte", "left": 8,
            "textStyle": {"color": COLORS["cyan_dark"], "fontSize": 13},
            "subtextStyle": {"color": COLORS["muted"]},
        },
        "tooltip": {
            "trigger": "item", "formatter": "{b}: {c} ({d}%)",
            "backgroundColor": COLORS["surface"], "borderColor": COLORS["border"],
            "textStyle": {"color": COLORS["text"]},
        },
        "legend": {"bottom": 0, "textStyle": {"color": COLORS["muted"]}},
        "graphic": [{
            "type": "text", "left": "center", "top": "46%", "silent": True,
            "style": {
                "text": f"{len(summary)}\nfornecedores", "fill": COLORS["text"],
                "fontSize": 13, "fontWeight": 800, "lineHeight": 19, "textAlign": "center",
            },
        }],
        "series": [{
            "type": "pie", "radius": ["48%", "72%"], "center": ["50%", "52%"],
            "avoidLabelOverlap": True,
            "label": {
                "show": True, "color": COLORS["text"], "fontSize": 11,
                "fontWeight": 700, "lineHeight": 16, "formatter": "{b}\n{c} · {d}%",
            },
            "labelLine": {"show": True, "length": 12, "length2": 8,
                          "lineStyle": {"color": COLORS["muted"]}},
            "itemStyle": {"borderColor": COLORS["surface"], "borderWidth": 3},
            "data": [
                {"value": below, "name": "Abaixo", "itemStyle": {"color": COLORS["danger"]}},
                {"value": within, "name": "Dentro", "itemStyle": {"color": COLORS["cyan"]}},
            ],
        }],
    }


def defects_chart(defects: pd.DataFrame) -> dict:
    view = defects.sort_values("defect_pieces")
    option = _base_option()
    option.update({
        "title": {
            "text": "Principais tipos de remonte", "subtext": "Peças com defeito",
            "textStyle": {"color": COLORS["cyan_dark"], "fontSize": 13},
            "subtextStyle": {"color": COLORS["muted"]},
        },
        "xAxis": {
            "type": "value", "splitNumber": 3,
            "axisLabel": {"color": COLORS["muted"], "hideOverlap": True},
            "axisLine": {"show": False}, "axisTick": {"show": False},
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "category", "data": view["defect_type"].tolist(),
            "axisLabel": {"color": COLORS["muted"], "width": 170, "overflow": "truncate"},
            "axisLine": {"show": False}, "axisTick": {"show": False},
        },
        "series": [{
            "type": "bar", "barWidth": 12,
            "data": view["defect_pieces"].round(0).tolist(),
            "label": {"show": True, "position": "right", "color": COLORS["text"],
                      "fontSize": 10, "fontWeight": 700},
            "itemStyle": {"color": COLORS["lime"], "borderRadius": [0, 7, 7, 0]},
        }],
    })
    return option


def trend_chart(trend: pd.DataFrame, target: float, frequency_label: str) -> dict:
    """Evolução da performance no tempo, contra a meta."""
    option = _base_option()
    option.update({
        "title": {
            "text": "Evolução da performance", "subtext": f"Agrupado por {frequency_label}",
            "textStyle": {"color": COLORS["cyan_dark"], "fontSize": 13},
            "subtextStyle": {"color": COLORS["muted"]},
        },
        "grid": {"left": 46, "right": 24, "top": 72, "bottom": 64},
        "xAxis": {
            "type": "category", "data": trend["period"].tolist(),
            "axisLabel": {"color": COLORS["muted"], "rotate": 40},
            "axisLine": {"show": False}, "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"formatter": "{value}%", "color": COLORS["muted"]},
            "axisLine": {"show": False}, "axisTick": {"show": False},
            "splitLine": {"lineStyle": {"color": COLORS["border"]}},
        },
        "series": [{
            "type": "line", "smooth": True, "symbolSize": 7,
            "data": [round(float(value) * 100, 2) for value in trend["performance"]],
            "lineStyle": {"color": COLORS["cyan"], "width": 3},
            "itemStyle": {"color": COLORS["cyan"]},
            "areaStyle": {"color": "rgba(0,184,132,0.12)"},
            "markLine": {
                "silent": True, "symbol": "none",
                "data": [{"yAxis": target * 100}],
                "lineStyle": {"color": COLORS["amber"], "type": "dashed"},
                "label": {"formatter": f"Meta {target:.0%}", "color": COLORS["amber"]},
            },
        }],
    })
    return option


def render_chart(option: dict, height: int, key: str) -> None:
    """Desenha uma spec pelo mesmo caminho dos gráficos do dashboard principal."""
    echart({"opts": option, "height": height}, key=key)


# ── Tabela ────────────────────────────────────────────────────────────────────

def html_table(
    frame: pd.DataFrame,
    columns: list[tuple[str, str, str]],
    target: float | None = None,
) -> None:
    """Tabela HTML com cabeçalho fixo e alinhamento numérico à direita.

    `columns` é uma lista de (chave, rótulo, tipo), com tipo em
    {text, number, minutes, percent, currency, date}.
    """
    if frame.empty:
        st.info("Nenhum registro encontrado para os filtros atuais.")
        return

    header = "".join(f"<th>{html.escape(label)}</th>" for _, label, _ in columns)
    body_rows: list[str] = []
    for _, row in frame.iterrows():
        cells: list[str] = []
        for key, _, kind in columns:
            value = row.get(key)
            css = "num" if kind in {"number", "percent", "minutes", "currency"} else ""
            if kind == "date":
                display = value.strftime("%d/%m/%Y") if pd.notna(value) else "—"
            elif kind == "percent":
                display = percent_br(value)
                if target is not None and key == "performance":
                    css += " bad-text" if float(value) < target else " good-text"
            elif kind == "number":
                display = number_br(value)
            elif kind == "minutes":
                display = number_br(value, 1)
            elif kind == "currency":
                display = currency_br(value)
            else:
                display = str(value) if pd.notna(value) else "—"
            cells.append(f'<td class="{css.strip()}">{html.escape(display)}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        f'<div class="perf-table-wrap"><table class="perf-table">'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


# ── Relatório para impressão ──────────────────────────────────────────────────
# Estes dois vivem em iframe (components.html) e por isso usam hex fixo: o
# documento do iframe não enxerga o :root da página, e relatório impresso é
# branco em qualquer tema — mesma regra de src/ui/preview.py.

def pdf_preview(pdf_bytes: bytes, height: int = 720) -> None:
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    render_html(
        f'<object data="data:application/pdf;base64,{encoded}" type="application/pdf" '
        f'width="100%" height="{height}px">'
        f'<div style="font-family:Inter,sans-serif;color:#4A5752;padding:24px;'
        f'background:#FFFFFF;border:1px solid #E8EFEC;border-radius:12px">'
        f"A pré-visualização não está disponível neste navegador. "
        f"Use o botão de download acima.</div></object>",
        height=height + 10,
        scrolling=False,
    )


def printable_report_preview(
    critical_orders: pd.DataFrame,
    supplier_summary: pd.DataFrame,
    target: float,
    threshold: float,
    period: str,
    height: int = 720,
) -> None:
    below = supplier_summary[supplier_summary["performance"] < target]
    visible = critical_orders.head(500)
    print_date = date_br(pd.Timestamp.now())

    def row_html(row) -> str:
        values = [
            html.escape(str(row.supplier)), html.escape(str(row.master_order)),
            html.escape(date_br(row.production_period)), number_br(row.real_cut),
            number_br(row.defect_pieces), percent_br(row.defect_rate),
            percent_br(row.performance), number_br(row.minutes_generated, 1),
            number_br(row.defect_cost, 2),
        ]
        return "<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>"

    rows = "".join(row_html(row) for row in visible.itertuples(index=False))
    if not rows:
        rows = '<tr><td colspan="9">Nenhuma ordem crítica para os filtros atuais.</td></tr>'

    truncated = ""
    if len(critical_orders) > len(visible):
        truncated = (
            f'<p class="note">Prévia limitada às primeiras {len(visible)} ordens. '
            f"O PDF contém todas as {len(critical_orders)} ordens.</p>"
        )

    total_cost = 0.0 if critical_orders.empty else float(critical_orders["defect_cost"].sum())
    total_pieces = 0 if critical_orders.empty else critical_orders["defect_pieces"].sum()

    render_html(
        f"""
        <style>
        * {{ box-sizing: border-box; }}
        @page {{ size:A4 landscape; margin:0; }}
        body {{ margin:0; background:#E8EFEC; color:#0D1B17; font-family:Arial,sans-serif; }}
        .toolbar {{ position:sticky; top:0; z-index:3; display:flex; justify-content:space-between;
                    align-items:center; padding:10px 16px; background:#0D1B17; color:white; }}
        button {{ border:1px solid #00B884; background:#F2F7F5; color:#0D1B17; border-radius:7px;
                  padding:8px 14px; font-weight:700; cursor:pointer; }}
        .page {{ width:calc(100% - 24px); margin:12px auto; padding:24px; background:white;
                 box-shadow:0 4px 18px rgba(13,27,23,.18); }}
        .report-heading {{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }}
        h1 {{ font-size:23px; margin:0 0 4px; color:#0D1B17; }}
        .print-date {{ color:#4A5752; font-size:11px; white-space:nowrap; padding-top:4px; }}
        .subtitle,.note {{ color:#4A5752; font-size:12px; }}
        .kpis {{ display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin:18px 0; }}
        .kpi {{ border:1px solid #E8EFEC; background:#F2F7F5; padding:10px; }}
        .kpi span {{ display:block; font-size:10px; text-transform:uppercase;
                     letter-spacing:.05em; color:#4A5752; }}
        .kpi strong {{ display:block; margin-top:5px; font-size:18px; color:#0D1B17; }}
        table {{ width:100%; border-collapse:collapse; font-size:10px; }}
        th {{ position:sticky; top:48px; background:#00B884; color:white; padding:7px; text-align:left; }}
        td {{ padding:6px 7px; border-bottom:1px solid #E8EFEC; }}
        tbody tr:nth-child(even) {{ background:#FAFCFB; }}
        @media print {{
          html, body, body * {{
            -webkit-print-color-adjust:exact !important;
            print-color-adjust:exact !important;
          }}
          body {{ background:white; }}
          .toolbar {{ display:none; }}
          .page {{ width:100%; margin:0; padding:16mm 12mm 12mm; box-shadow:none; }}
          .kpi {{ background:#F2F7F5 !important; border-color:#E8EFEC !important; }}
          th {{ position:static; background:#00B884 !important; color:white !important; }}
          tbody tr:nth-child(even) {{ background:#FAFCFB !important; }}
          table {{ font-size:8px; }}
        }}
        </style>
        <div class="toolbar"><strong>Pré-visualização para impressão</strong>
        <button onclick="window.print()">Imprimir esta visualização</button></div>
        <main class="page">
          <div class="report-heading">
            <h1>PERFORMANCE DE FORNECEDORES</h1>
            <div class="print-date">Impresso em: {print_date}</div>
          </div>
          <div class="subtitle">Período: {html.escape(date_br(period))} ·
          Meta: {target:.1%} · Corte de perda: {threshold:.1%}</div>
          <section class="kpis">
            <div class="kpi"><span>Fornecedores</span><strong>{len(supplier_summary)}</strong></div>
            <div class="kpi"><span>Abaixo da meta</span><strong>{len(below)}</strong></div>
            <div class="kpi"><span>Ordens críticas</span><strong>{len(critical_orders)}</strong></div>
            <div class="kpi"><span>Peças perdidas</span><strong>{number_br(total_pieces)}</strong></div>
            <div class="kpi"><span>Custo das perdas</span><strong>{currency_br(total_cost)}</strong></div>
          </section>
          <h2>Ordens críticas</h2>
          {truncated}
          <table><thead><tr><th>Fornecedor</th><th>Ordem mestre</th><th>Data de produção</th>
          <th>Real cortado</th><th>Perdas</th><th>% perda</th><th>Performance</th>
          <th>Minutos</th><th>Custo (R$)</th></tr></thead><tbody>{rows}</tbody></table>
        </main>
        """,
        height=height,
        scrolling=True,
    )
