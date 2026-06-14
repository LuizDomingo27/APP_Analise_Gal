"""
Chart builder layer.
Pure functions: receive DataFrames, return Plotly Figure objects.
No Streamlit, no business logic.
"""

import plotly.graph_objects as go
import pandas as pd
from src.config.settings import COLS, COLORS, DEFECT_COLORS, PLOTLY_BASE, AXIS_X, AXIS_Y


# ── Helpers ───────────────────────────────────────────────────────────────────

def _layout(**overrides) -> dict:
    """Merge PLOTLY_BASE with per-chart overrides."""
    return {**PLOTLY_BASE, **overrides}


def _hbar_margin(label_chars: int = 25) -> dict:
    """Left margin sized to the longest y-axis label; right margin for outside text."""
    return {"t": 40, "b": 30, "l": max(160, label_chars * 7), "r": 110}


def _xrange_pad(series: pd.Series, pct: float = 0.32) -> list:
    """Extend x-axis beyond max so outside text labels are never clipped."""
    mx = float(series.max()) if len(series) > 0 else 1.0
    return [0, mx * (1 + pct)]


def _sparse_text(series: pd.Series, fmt_fn, max_labels: int = 15) -> list[str]:
    """
    Return formatted labels for at most max_labels points, evenly spaced.
    Prevents overlap on dense area/line charts.
    """
    n = len(series)
    if n == 0:
        return []
    if n <= max_labels:
        return [fmt_fn(v) for v in series]
    step = max(1, (n - 1) // (max_labels - 1))
    return [fmt_fn(v) if i % step == 0 else "" for i, v in enumerate(series)]


# ── Donut – defect type ───────────────────────────────────────────────────────

def donut_defect_type(df: pd.DataFrame) -> go.Figure:
    total = int(df[COLS["quantity"]].sum())
    colors = [DEFECT_COLORS.get(d, COLORS["gray"]) for d in df[COLS["defect"]]]

    fig = go.Figure(
        go.Pie(
            labels=df[COLS["defect"]],
            values=df[COLS["quantity"]],
            hole=0.55,
            marker=dict(colors=colors, line=dict(color="#0D0D1A", width=2)),
            textinfo="percent+label",
            textposition="outside",
            textfont=dict(size=12, color="#C8C0F0"),
            insidetextorientation="radial",
            outsidetextfont=dict(size=11, color="#C8C0F0"),
            hovertemplate="<b>%{label}</b><br>Qtd: %{value:,}<br>%{percent}<extra></extra>",
            pull=[0.04 if i == 0 else 0 for i in range(len(df))],
        )
    )
    fig.update_layout(
        **_layout(height=380, margin={"t": 50, "b": 50, "l": 90, "r": 90}),
        annotations=[dict(
            text=f"<b>{total:,}</b><br><span style='font-size:10px'>peças</span>",
            x=0.5, y=0.5, font=dict(size=18, color="#E8E8FF"),
            showarrow=False,
        )],
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


# ── Horizontal bar – location ─────────────────────────────────────────────────

def bar_location(df: pd.DataFrame) -> go.Figure:
    d = df.sort_values(COLS["quantity"], ascending=True)
    fig = go.Figure(
        go.Bar(
            x=d[COLS["quantity"]],
            y=d[COLS["location"]],
            orientation="h",
            marker=dict(
                color=d[COLS["quantity"]],
                colorscale=[[0, "#2A2470"], [0.5, "#534AB7"], [1, "#9D97F0"]],
                line=dict(width=0),
            ),
            text=d[COLS["quantity"]].apply(lambda v: f"{v:,}"),
            textposition="outside",
            textfont=dict(color="#C8C0F0", size=12, family="Inter, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Qtd: %{x:,}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(
            height=max(320, len(d) * 42 + 80),
            margin=_hbar_margin(12),
        ),
        xaxis={**AXIS_X, "showgrid": True, "range": _xrange_pad(d[COLS["quantity"]])},
        yaxis={**AXIS_Y},
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


# ── Horizontal bar – supplier quantity ────────────────────────────────────────

def bar_supplier_quantity(df: pd.DataFrame) -> go.Figure:
    d = df.sort_values(COLS["quantity"], ascending=True).copy()
    d["label"] = d[COLS["supplier"]].str[:28]
    fig = go.Figure(
        go.Bar(
            x=d[COLS["quantity"]],
            y=d["label"],
            orientation="h",
            marker=dict(
                color=d[COLS["quantity"]],
                colorscale=[[0, "#0B4A35"], [0.5, "#0F8060"], [1, "#1DC99A"]],
                line=dict(width=0),
            ),
            text=d[COLS["quantity"]].apply(lambda v: f"{v:,}"),
            textposition="outside",
            textfont=dict(color="#C8C0F0", size=12, family="Inter, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Qtd: %{x:,}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(height=max(340, len(d) * 42 + 80), margin=_hbar_margin(28)),
        xaxis={**AXIS_X, "showgrid": True, "range": _xrange_pad(d[COLS["quantity"]])},
        yaxis={**AXIS_Y},
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


# ── Horizontal bar – supplier cost ────────────────────────────────────────────

def bar_supplier_cost(df: pd.DataFrame) -> go.Figure:
    d = df.sort_values(COLS["value_brl"], ascending=True).copy()
    d["label"] = d[COLS["supplier"]].str[:28]
    fig = go.Figure(
        go.Bar(
            x=d[COLS["value_brl"]],
            y=d["label"],
            orientation="h",
            marker=dict(
                color=d[COLS["value_brl"]],
                colorscale=[[0, "#6B1A0E"], [0.5, "#C04428"], [1, "#F07555"]],
                line=dict(width=0),
            ),
            text=d[COLS["value_brl"]].apply(lambda v: f"R${v:,.0f}"),
            textposition="outside",
            textfont=dict(color="#C8C0F0", size=12, family="Inter, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Custo: R$%{x:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(height=max(340, len(d) * 42 + 80), margin=_hbar_margin(28)),
        xaxis={
            **AXIS_X,
            "showgrid": True,
            "tickprefix": "R$",
            "range": _xrange_pad(d[COLS["value_brl"]]),
        },
        yaxis={**AXIS_Y},
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


# ── Horizontal bar – supplier remonte rate ────────────────────────────────────

def bar_supplier_rate(df: pd.DataFrame) -> go.Figure:
    d = df.sort_values(COLS["pct_remonte"], ascending=True).copy()
    d["label"] = d[COLS["supplier"]].str[:28]
    fig = go.Figure(
        go.Bar(
            x=d[COLS["pct_remonte"]],
            y=d["label"],
            orientation="h",
            marker=dict(
                color=d[COLS["pct_remonte"]],
                colorscale=[[0, "#5A3A08"], [0.5, "#B07820"], [1, "#F0B840"]],
                line=dict(width=0),
            ),
            text=d[COLS["pct_remonte"]].apply(lambda v: f"{v:.2f}%"),
            textposition="outside",
            textfont=dict(color="#C8C0F0", size=12, family="Inter, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Taxa: %{x:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(height=max(340, len(d) * 42 + 80), margin=_hbar_margin(28)),
        xaxis={
            **AXIS_X,
            "showgrid": True,
            "ticksuffix": "%",
            "range": _xrange_pad(d[COLS["pct_remonte"]]),
        },
        yaxis={**AXIS_Y},
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


# ── Horizontal bar – key combinations ────────────────────────────────────────

def bar_key_combinations(df: pd.DataFrame) -> go.Figure:
    d = df.copy()
    d["combo"] = d[COLS["location"]] + " / " + d[COLS["defect"]]
    d = d.sort_values(COLS["quantity"], ascending=True)
    bar_colors = [
        DEFECT_COLORS.get(row[COLS["defect"]], COLORS["gray"])
        for _, row in d.iterrows()
    ]
    fig = go.Figure(
        go.Bar(
            x=d[COLS["quantity"]],
            y=d["combo"],
            orientation="h",
            marker=dict(
                color=bar_colors,
                line=dict(color="rgba(255,255,255,0.06)", width=1),
            ),
            text=d[COLS["quantity"]].apply(lambda v: f"{v:,}"),
            textposition="outside",
            textfont=dict(color="#C8C0F0", size=12, family="Inter, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Qtd: %{x:,}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(height=max(340, len(d) * 38 + 80), margin=_hbar_margin(32)),
        xaxis={**AXIS_X, "showgrid": True, "range": _xrange_pad(d[COLS["quantity"]])},
        yaxis={**AXIS_Y},
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig


# ── Area – defects by date ────────────────────────────────────────────────────

def area_defects_by_date(df: pd.DataFrame) -> go.Figure:
    labels = _sparse_text(df[COLS["quantity"]], lambda v: f"{v:,}")
    fig = go.Figure(
        go.Scatter(
            x=df[COLS["date"]],
            y=df[COLS["quantity"]],
            mode="lines+markers+text",
            line=dict(color=COLORS["primary"], width=2.5, shape="spline", smoothing=0.5),
            marker=dict(
                size=8,
                color=COLORS["primary"],
                line=dict(color="#0D0D1A", width=2),
                symbol="circle",
            ),
            text=labels,
            textposition="top center",
            textfont=dict(color="#C8C0F0", size=11, family="Inter, sans-serif"),
            cliponaxis=False,
            fill="tozeroy",
            fillcolor="rgba(83,74,183,0.12)",
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Defeitos: %{y:,}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(height=330, margin={"t": 64, "b": 36, "l": 52, "r": 30}),
        xaxis={**AXIS_X, "showgrid": False, "tickformat": "%d/%m"},
        yaxis={**AXIS_X, "showgrid": True, "autorange": True},
    )
    return fig


# ── Area – cost by date ───────────────────────────────────────────────────────

def area_cost_by_date(df: pd.DataFrame) -> go.Figure:
    labels = _sparse_text(df[COLS["value_brl"]], lambda v: f"R${v:,.0f}")
    fig = go.Figure(
        go.Scatter(
            x=df[COLS["date"]],
            y=df[COLS["value_brl"]],
            mode="lines+markers+text",
            line=dict(color=COLORS["coral"], width=2.5, shape="spline", smoothing=0.5),
            marker=dict(
                size=8,
                color=COLORS["coral"],
                line=dict(color="#0D0D1A", width=2),
                symbol="circle",
            ),
            text=labels,
            textposition="top center",
            textfont=dict(color="#C8C0F0", size=11, family="Inter, sans-serif"),
            cliponaxis=False,
            fill="tozeroy",
            fillcolor="rgba(216,90,48,0.12)",
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Custo: R$%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **_layout(height=330, margin={"t": 64, "b": 36, "l": 70, "r": 30}),
        xaxis={**AXIS_X, "showgrid": False, "tickformat": "%d/%m"},
        yaxis={**AXIS_X, "showgrid": True, "tickprefix": "R$", "autorange": True},
    )
    return fig
