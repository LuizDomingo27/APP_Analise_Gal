"""
Chart builder layer (Apache ECharts via streamlit-echarts).

Pure functions: receive DataFrames, return ECharts *option dicts*.
No Streamlit, no business logic. The rendering (st_echarts) lives in
`src.charts.render`, so these functions stay easy to test/inspect.

Each function returns a spec ``{"opts": <echarts option dict>, "height": <int px>}``.
JavaScript callbacks (label/tooltip formatters) are embedded with
``streamlit_echarts.JsCode(...).js_code`` tokens, which the component
expands on the client side.
"""

import pandas as pd
from streamlit_echarts import JsCode

from src.config.settings import COLS, DEFECT_COLORS, ECHARTS_FONT, TEXT_MUTED, TEXT_PRIMARY

# ── Shared style tokens ───────────────────────────────────────────────────────

_ARC_STROKE = "#FAFCFB"
_GRID_LINE = "rgba(0,0,0,0.10)"

# Gradients (low → high) reused across the horizontal bars.
_GREEN = ("#00805C", "#5FF6C6")
_RED = ("#9A2A14", "#F07555")
_AMBER = ("#7A5210", "#F0B840")


def _js(code: str) -> str:
    """Wrap a JS snippet as a token that streamlit-echarts expands client-side."""
    return JsCode(code).js_code


def _text_style(**over) -> dict:
    base = {"fontFamily": ECHARTS_FONT, "color": TEXT_MUTED}
    base.update(over)
    return base


def _empty(height: int, msg: str = "Sem dados no período") -> dict:
    """Placeholder option shown when a DataFrame is empty."""
    return {
        "opts": {
            "backgroundColor": "transparent",
            "graphic": {
                "type": "text",
                "left": "center",
                "top": "middle",
                "style": {"text": msg, "fill": TEXT_MUTED, "font": f"13px {ECHARTS_FONT}"},
            },
        },
        "height": height,
    }


# ── pt-BR number formatters (client-side) ─────────────────────────────────────

_FMT_INT = _js("function(p){return Math.round(p.value).toLocaleString('pt-BR');}")
_FMT_BRL = _js(
    "function(p){return 'R$ '+Number(p.value).toLocaleString('pt-BR',"
    "{minimumFractionDigits:2,maximumFractionDigits:2});}"
)
_FMT_PCT2 = _js("function(p){return Number(p.value).toFixed(2).replace('.',',');}")


# ── Modern tooltip ────────────────────────────────────────────────────────────
# Dark, rounded, soft-shadow card with a coloured marker, muted caption and a
# large value — shared by every chart for a consistent, modern look.

_TOOLTIP_STYLE = {
    "backgroundColor": "rgba(13,27,23,0.94)",
    "borderColor": "rgba(255,255,255,0.10)",
    "borderWidth": 1,
    "padding": [10, 14],
    "textStyle": {"color": "#FAFCFB", "fontFamily": ECHARTS_FONT, "fontSize": 12},
    "extraCssText": "border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.28);",
}

# HTML pieces shared by the item/axis tooltip builders. NAME/VALUE/SUB are JS
# expressions the caller supplies; `c` is the marker colour (item colour).
_TIP_OPEN = "'<div style=\"font-family:Inter,sans-serif;min-width:118px\">'"
_TIP_CLOSE = "'</div>'"
_TIP_MARKER = (
    "+'<span style=\"width:9px;height:9px;border-radius:3px;display:inline-block;"
    "background:'+c+'\"></span>'"
)


def _tooltip(formatter: str, trigger: str = "item", axis_pointer: dict | None = None) -> dict:
    t = dict(_TOOLTIP_STYLE)
    t["trigger"] = trigger
    t["formatter"] = formatter
    if axis_pointer is not None:
        t["axisPointer"] = axis_pointer
    return t


def _tip_body(name_expr: str, value_expr: str, sub_expr: str) -> str:
    """The inner HTML (header + value + optional sub-line), sans the wrapper."""
    return (
        "'<div style=\"display:flex;align-items:center;gap:6px;margin-bottom:5px\">'"
        + _TIP_MARKER
        + "+'<span style=\"font-size:11px;color:#C2CDC9;font-weight:500\">'+("
        + name_expr + ")+'</span></div>'"
        + "+'<div style=\"font-size:16px;font-weight:700;color:#FFFFFF;line-height:1.15\">'+("
        + value_expr + ")+'</div>'"
        + "+((" + sub_expr + ")?'<div style=\"font-size:11px;color:#8FA09A;margin-top:3px\">'+("
        + sub_expr + ")+'</div>':'')"
    )


def _tip_item(name_expr: str, value_expr: str, sub_expr: str = "''") -> str:
    """Modern HTML tooltip for `trigger:'item'` (pie / bar) charts."""
    return _js(
        "function(p){var c=p.color;return "
        + _TIP_OPEN + "+" + _tip_body(name_expr, value_expr, sub_expr) + "+" + _TIP_CLOSE + ";}"
    )


def _tip_axis(name_expr: str, value_expr: str, sub_expr: str = "''") -> str:
    """Modern HTML tooltip for `trigger:'axis'` (line/area) charts."""
    return _js(
        "function(a){var p=a[0];var c=p.color;return "
        + _TIP_OPEN + "+" + _tip_body(name_expr, value_expr, sub_expr) + "+" + _TIP_CLOSE + ";}"
    )


# ── Donut – defect type ───────────────────────────────────────────────────────

def donut_defect_type(df: pd.DataFrame) -> dict:
    if df.empty:
        return _empty(460)

    total = int(df[COLS["quantity"]].sum())

    # Order slices by the canonical defect order so colours stay stable.
    order = {name: i for i, name in enumerate(DEFECT_COLORS)}
    d = df.copy()
    d["_k"] = d[COLS["defect"]].map(order).fillna(len(order))
    d = d.sort_values("_k")

    data = [
        {
            "name": str(row[COLS["defect"]]),
            "value": int(row[COLS["quantity"]]),
            "itemStyle": {"color": DEFECT_COLORS.get(row[COLS["defect"]], "#7C8985")},
        }
        for _, row in d.iterrows()
    ]

    opts = {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": ECHARTS_FONT},
        "tooltip": _tooltip(
            _tip_item(
                "p.name",
                "p.value.toLocaleString('pt-BR')+' peças'",
                "p.percent+'% do total'",
            )
        ),
        # Total no centro do anel.
        "title": {
            "text": f"{total:,}".replace(",", "."),
            "subtext": "peças",
            "left": "center",
            "top": "center",
            "textAlign": "center",
            "textStyle": {"fontSize": 24, "fontWeight": "bold", "color": TEXT_PRIMARY},
            "subtextStyle": {"fontSize": 12, "color": TEXT_MUTED},
        },
        "series": [
            {
                "type": "pie",
                # Anel maior; rótulos vão para fora com linha-guia (avoidLabelOverlap).
                "radius": ["46%", "72%"],
                "center": ["46%", "51%"],
                "avoidLabelOverlap": True,
                "minAngle": 4,
                "itemStyle": {
                    "borderColor": _ARC_STROKE,
                    "borderWidth": 2,
                    "borderRadius": 4,
                },
                # Só a % fica fora do anel (nomes já estão na legenda de cores
                # acima do gráfico), evitando corte de rótulos longos na coluna.
                "label": {
                    "show": True,
                    "position": "outside",
                    "formatter": _js("function(p){return p.percent+'%';}"),
                    "fontSize": 12,
                    "fontWeight": "bold",
                    "color": TEXT_PRIMARY,
                },
                "labelLine": {"show": True, "length": 12, "length2": 10, "smooth": True},
                "data": data,
            }
        ],
    }
    return {"opts": opts, "height": 460}


# ── Horizontal bars ───────────────────────────────────────────────────────────

def _hbar(
    df: pd.DataFrame,
    cat_col: str,
    val_col: str,
    gradient: tuple[str, str],
    value_fmt: str,
    height: int,
    tooltip_title: str,
    tooltip_fmt: str,
) -> dict:
    """Generic horizontal bar with a value-driven colour gradient (visualMap)."""
    if df.empty:
        return _empty(height)

    # ECharts places category index 0 at the bottom → sort ascending so the
    # largest value ends up on top, matching the old Altair layout.
    d = df.sort_values(val_col, ascending=True)
    cats = [str(x)[:28] for x in d[cat_col]]
    vals = [round(float(x), 4) for x in d[val_col]]
    lo, hi = min(vals), max(vals)
    if lo == hi:  # single value / all-equal → avoid a degenerate visualMap
        lo = 0.0

    opts = {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": ECHARTS_FONT},
        "grid": {"left": 6, "right": 64, "top": 6, "bottom": 6, "containLabel": True},
        "tooltip": _tooltip(_tip_item("p.name", tooltip_fmt, "'" + tooltip_title + "'")),
        "xAxis": {"type": "value", "show": False, "max": round(hi * 1.28, 4)},
        "yAxis": {
            "type": "category",
            "data": cats,
            "axisTick": {"show": False},
            "axisLine": {"show": False},
            "axisLabel": _text_style(fontSize=12),
        },
        "visualMap": {
            "show": False,
            "min": lo,
            "max": hi,
            "dimension": 0,
            "inRange": {"color": list(gradient)},
        },
        "series": [
            {
                "type": "bar",
                "data": vals,
                "itemStyle": {"borderRadius": [0, 4, 4, 0]},
                "label": {
                    "show": True,
                    "position": "right",
                    "formatter": value_fmt,
                    "fontSize": 11,
                    "color": TEXT_MUTED,
                },
            }
        ],
    }
    return {"opts": opts, "height": height}


def bar_location(df: pd.DataFrame, top: int = 10) -> dict:
    d = df.sort_values(COLS["quantity"], ascending=False).head(top)
    return _hbar(
        d, COLS["location"], COLS["quantity"], _GREEN,
        _FMT_INT, 400, "Qtd",
        "p.value.toLocaleString('pt-BR')",
    )


def bar_supplier_quantity(df: pd.DataFrame) -> dict:
    d = df.sort_values(COLS["quantity"], ascending=False)
    h = max(340, len(d) * 42 + 80)
    return _hbar(
        d, COLS["supplier"], COLS["quantity"], _GREEN,
        _FMT_INT, h, "Qtd",
        "p.value.toLocaleString('pt-BR')",
    )


def bar_supplier_cost(df: pd.DataFrame) -> dict:
    d = df.sort_values(COLS["value_brl"], ascending=False)
    h = max(340, len(d) * 42 + 80)
    return _hbar(
        d, COLS["supplier"], COLS["value_brl"], _RED,
        _FMT_BRL, h, "Custo (R$)",
        "'R$ '+Number(p.value).toLocaleString('pt-BR',{minimumFractionDigits:2})",
    )


def bar_supplier_rate(df: pd.DataFrame) -> dict:
    d = df.sort_values(COLS["pct_remonte"], ascending=False)
    h = max(340, len(d) * 42 + 80)
    return _hbar(
        d, COLS["supplier"], COLS["pct_remonte"], _AMBER,
        _FMT_PCT2, h, "Taxa (%)",
        "Number(p.value).toFixed(2).replace('.',',')+'%'",
    )


# ── Horizontal bar – key combinations (coloured by defect type) ───────────────

def bar_key_combinations(df: pd.DataFrame) -> dict:
    height = max(340, len(df) * 38 + 80)
    if df.empty:
        return _empty(height)

    d = df.copy()
    d["_combo"] = d[COLS["location"]].astype(str) + " / " + d[COLS["defect"]].astype(str)
    d = d.sort_values(COLS["quantity"], ascending=True)  # ascending → max on top

    cats = d["_combo"].tolist()
    data = [
        {
            "value": int(row[COLS["quantity"]]),
            "itemStyle": {"color": DEFECT_COLORS.get(row[COLS["defect"]], "#7C8985")},
        }
        for _, row in d.iterrows()
    ]
    top_val = float(d[COLS["quantity"]].max())

    opts = {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": ECHARTS_FONT},
        "grid": {"left": 6, "right": 56, "top": 6, "bottom": 6, "containLabel": True},
        "tooltip": _tooltip(
            _tip_item("p.name", "p.value.toLocaleString('pt-BR')", "'Quantidade'")
        ),
        "xAxis": {"type": "value", "show": False, "max": round(top_val * 1.28, 2)},
        "yAxis": {
            "type": "category",
            "data": cats,
            "axisTick": {"show": False},
            "axisLine": {"show": False},
            "axisLabel": _text_style(fontSize=12),
        },
        "series": [
            {
                "type": "bar",
                "data": data,
                "itemStyle": {"borderRadius": [0, 4, 4, 0]},
                "label": {
                    "show": True,
                    "position": "right",
                    "formatter": _FMT_INT,
                    "fontSize": 11,
                    "color": TEXT_MUTED,
                },
            }
        ],
    }
    return {"opts": opts, "height": height}


# ── Area/line by date ─────────────────────────────────────────────────────────

def _line_by_date(
    df: pd.DataFrame,
    val_col: str,
    line_color: str,
    area_color: str,
    mean_color: str,
    value_expr: str,
    metric_label: str,
    mean_fmt: str,
) -> dict:
    height = 330
    if df.empty:
        return _empty(height)

    d = df.sort_values(COLS["date"])
    x = [pd.Timestamp(dt).strftime("%d/%m/%Y") for dt in d[COLS["date"]]]
    y = [round(float(v), 2) for v in d[val_col]]

    opts = {
        "backgroundColor": "transparent",
        "textStyle": {"fontFamily": ECHARTS_FONT},
        "grid": {"left": 6, "right": 24, "top": 24, "bottom": 6, "containLabel": True},
        "tooltip": _tooltip(
            _tip_axis("p.axisValue", value_expr, "'" + metric_label + "'"),
            trigger="axis",
            axis_pointer={"type": "line", "lineStyle": {"color": "rgba(0,0,0,0.14)", "width": 1}},
        ),
        "xAxis": {
            "type": "category",
            "data": x,
            "boundaryGap": False,
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": _GRID_LINE}},
            # Rótulo do eixo mostra apenas dd/mm; tooltip mantém o ano.
            "axisLabel": _text_style(
                fontSize=11,
                formatter=_js("function(v){return v.slice(0,5);}"),
            ),
        },
        "yAxis": {"type": "value", "show": False},
        "series": [
            {
                "type": "line",
                "data": y,
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 8,
                "lineStyle": {"color": line_color, "width": 2.5},
                "itemStyle": {"color": line_color},
                "areaStyle": {"color": area_color},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"color": mean_color, "type": "dashed", "width": 1.5},
                    "data": [{"type": "average", "name": "Média"}],
                    "label": {
                        "formatter": mean_fmt,
                        "position": "insideEndTop",
                        "color": mean_color,
                        "fontWeight": "bold",
                        "fontSize": 11,
                    },
                },
            }
        ],
    }
    return {"opts": opts, "height": height}


def area_defects_by_date(df: pd.DataFrame) -> dict:
    return _line_by_date(
        df, COLS["quantity"],
        line_color="#00B884",
        area_color="rgba(0,184,132,0.12)",
        mean_color="#00805C",
        value_expr="p.value.toLocaleString('pt-BR')+' defeitos'",
        metric_label="Defeitos no dia",
        mean_fmt=_js(
            "function(p){return 'Média: '+Number(p.value).toFixed(1).replace('.',',');}"
        ),
    )


def area_cost_by_date(df: pd.DataFrame) -> dict:
    return _line_by_date(
        df, COLS["value_brl"],
        line_color="#D85A30",
        area_color="rgba(216,90,48,0.12)",
        mean_color="#A83F1B",
        value_expr=(
            "'R$ '+Number(p.value).toLocaleString('pt-BR',{minimumFractionDigits:2})"
        ),
        metric_label="Custo no dia",
        mean_fmt=_js(
            "function(p){return 'Média: R$ '+Number(p.value).toLocaleString('pt-BR',"
            "{minimumFractionDigits:2,maximumFractionDigits:2});}"
        ),
    )
