"""
Chart builder layer.
Pure functions: receive DataFrames, return Altair Chart objects.
No Streamlit, no business logic.
"""

import altair as alt
import pandas as pd
from src.config.settings import COLS, COLORS, DEFECT_COLORS, ALTAIR_CONFIG


def _configure(chart: alt.Chart) -> alt.Chart:
    """Apply consistent app-wide styling to a chart."""
    return chart.configure(**ALTAIR_CONFIG)


# ── Donut – defect type ───────────────────────────────────────────────────────

def donut_defect_type(df: pd.DataFrame) -> alt.Chart:
    total = int(df[COLS["quantity"]].sum())
    d = df.copy()
    d["_pct"] = (d[COLS["quantity"]] / total * 100).round(1)
    d["_pct_label"] = d["_pct"].astype(str) + "%"
    d["_name"] = d[COLS["defect"]].str[:20]
    # Oculta rótulos de fatias menores que 3% para evitar sobreposição
    d["_name_shown"] = d.apply(lambda r: r["_name"] if r["_pct"] >= 3 else "", axis=1)
    d["_pct_shown"] = d.apply(lambda r: r["_pct_label"] if r["_pct"] >= 3 else "", axis=1)

    domain_order = list(DEFECT_COLORS.keys())
    sort_map = {v: i for i, v in enumerate(domain_order)}
    d["_sort_key"] = d[COLS["defect"]].map(sort_map).fillna(len(domain_order))
    d = d.sort_values("_sort_key").reset_index(drop=True)

    theta = alt.Theta(field=COLS["quantity"], type="quantitative", stack=True)
    color_enc = alt.Color(
        field=COLS["defect"],
        type="nominal",
        scale=alt.Scale(
            domain=list(DEFECT_COLORS.keys()),
            range=list(DEFECT_COLORS.values()),
        ),
        legend=None,
    )

    order_enc = alt.Order(field="_sort_key", sort="ascending")

    arc = (
        alt.Chart(d)
        .mark_arc(innerRadius=110, outerRadius=185, stroke="#FAFCFB", strokeWidth=2)
        .encode(
            theta=theta,
            color=color_enc,
            order=order_enc,
            tooltip=[
                alt.Tooltip(field=COLS["defect"], type="nominal", title="Tipo"),
                alt.Tooltip(field=COLS["quantity"], type="quantitative", title="Qtd", format=",d"),
                alt.Tooltip(field="_pct", type="quantitative", title="%", format=".1f"),
            ],
        )
        .properties(width=520, height=520)
    )

    label_name = (
        alt.Chart(d)
        .mark_text(radius=220, fontSize=11, color="#0D1B17", fontWeight="bold", dy=-8)
        .encode(theta=theta, order=order_enc, text=alt.Text(field="_name_shown"))
    )

    label_pct = (
        alt.Chart(d)
        .mark_text(radius=220, fontSize=10, color="#4A5752", dy=8)
        .encode(theta=theta, order=order_enc, text=alt.Text(field="_pct_shown"))
    )

    center_total = (
        alt.Chart(pd.DataFrame([{"v": f"{total:,}"}]))
        .mark_text(fontSize=28, fontWeight="bold", color="#0D1B17", dy=-10)
        .encode(text=alt.Text(field="v", type="nominal"))
    )
    center_label = (
        alt.Chart(pd.DataFrame([{"v": "peças"}]))
        .mark_text(fontSize=13, color="#4A5752", dy=18)
        .encode(text=alt.Text(field="v", type="nominal"))
    )

    return _configure(arc + label_name + label_pct + center_total + center_label)


# ── Horizontal bar – location ─────────────────────────────────────────────────

def bar_location(df: pd.DataFrame) -> alt.Chart:
    d = df.sort_values(COLS["quantity"], ascending=False)
    h = max(320, len(d) * 42 + 80)

    bars = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            x=alt.X(
                field=COLS["quantity"], type="quantitative",
                axis=alt.Axis(title=None, grid=False),
            ),
            y=alt.Y(
                field=COLS["location"], type="nominal",
                sort=alt.EncodingSortField(field=COLS["quantity"], order="descending"),
                axis=alt.Axis(title=None),
            ),
            color=alt.Color(
                field=COLS["quantity"], type="quantitative",
                scale=alt.Scale(range=["#00805C", "#5FF6C6"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(field=COLS["location"], type="nominal", title="Local"),
                alt.Tooltip(field=COLS["quantity"], type="quantitative", title="Qtd", format=",d"),
            ],
        )
    )

    text = bars.mark_text(align="left", dx=5, color="#4A5752", fontSize=11).encode(
        text=alt.Text(field=COLS["quantity"], type="quantitative", format=",d"),
        color=alt.value("#4A5752"),
    )

    return _configure((bars + text).properties(height=h))


# ── Horizontal bar – supplier quantity ────────────────────────────────────────

def bar_supplier_quantity(df: pd.DataFrame) -> alt.Chart:
    d = df.sort_values(COLS["quantity"], ascending=False).copy()
    d["_label"] = d[COLS["supplier"]].str[:28]
    h = max(340, len(d) * 42 + 80)

    bars = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            x=alt.X(
                field=COLS["quantity"], type="quantitative",
                axis=alt.Axis(title=None, grid=False),
            ),
            y=alt.Y(
                field="_label", type="nominal",
                sort=alt.EncodingSortField(field=COLS["quantity"], order="descending"),
                axis=alt.Axis(title=None),
            ),
            color=alt.Color(
                field=COLS["quantity"], type="quantitative",
                scale=alt.Scale(range=["#00805C", "#5FF6C6"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(field=COLS["supplier"], type="nominal", title="Fornecedor"),
                alt.Tooltip(field=COLS["quantity"], type="quantitative", title="Qtd", format=",d"),
            ],
        )
    )

    text = bars.mark_text(align="left", dx=5, fontSize=11).encode(
        text=alt.Text(field=COLS["quantity"], type="quantitative", format=",d"),
        color=alt.value("#4A5752"),
    )

    return _configure((bars + text).properties(height=h))


# ── Horizontal bar – supplier cost ────────────────────────────────────────────

def bar_supplier_cost(df: pd.DataFrame) -> alt.Chart:
    d = df.sort_values(COLS["value_brl"], ascending=False).copy()
    d["_label"] = d[COLS["supplier"]].str[:28]
    h = max(340, len(d) * 42 + 80)

    bars = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            x=alt.X(
                field=COLS["value_brl"], type="quantitative",
                axis=alt.Axis(title=None, grid=False, format="$,.0f"),
            ),
            y=alt.Y(
                field="_label", type="nominal",
                sort=alt.EncodingSortField(field=COLS["value_brl"], order="descending"),
                axis=alt.Axis(title=None),
            ),
            color=alt.Color(
                field=COLS["value_brl"], type="quantitative",
                scale=alt.Scale(range=["#9A2A14", "#F07555"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(field=COLS["supplier"], type="nominal", title="Fornecedor"),
                alt.Tooltip(field=COLS["value_brl"], type="quantitative", title="Custo (R$)", format=",.2f"),
            ],
        )
    )

    text = bars.mark_text(align="left", dx=5, fontSize=11).encode(
        text=alt.Text(field=COLS["value_brl"], type="quantitative", format="$,.0f"),
        color=alt.value("#4A5752"),
    )

    return _configure((bars + text).properties(height=h))


# ── Horizontal bar – supplier remonte rate ────────────────────────────────────

def bar_supplier_rate(df: pd.DataFrame) -> alt.Chart:
    d = df.sort_values(COLS["pct_remonte"], ascending=False).copy()
    d["_label"] = d[COLS["supplier"]].str[:28]
    h = max(340, len(d) * 42 + 80)

    bars = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            x=alt.X(
                field=COLS["pct_remonte"], type="quantitative",
                axis=alt.Axis(title=None, grid=False, format=".2f"),
            ),
            y=alt.Y(
                field="_label", type="nominal",
                sort=alt.EncodingSortField(field=COLS["pct_remonte"], order="descending"),
                axis=alt.Axis(title=None),
            ),
            color=alt.Color(
                field=COLS["pct_remonte"], type="quantitative",
                scale=alt.Scale(range=["#7A5210", "#F0B840"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(field=COLS["supplier"], type="nominal", title="Fornecedor"),
                alt.Tooltip(field=COLS["pct_remonte"], type="quantitative", title="Taxa (%)", format=".2f"),
            ],
        )
    )

    text = bars.mark_text(align="left", dx=5, fontSize=11).encode(
        text=alt.Text(field=COLS["pct_remonte"], type="quantitative", format=".2f"),
        color=alt.value("#4A5752"),
    )

    return _configure((bars + text).properties(height=h))


# ── Horizontal bar – key combinations ────────────────────────────────────────

def bar_key_combinations(df: pd.DataFrame) -> alt.Chart:
    d = df.copy()
    d["_combo"] = d[COLS["location"]] + " / " + d[COLS["defect"]]
    d = d.sort_values(COLS["quantity"], ascending=False)
    h = max(340, len(d) * 38 + 80)

    color_domain = list(DEFECT_COLORS.keys())
    color_range  = list(DEFECT_COLORS.values())

    bars = (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            x=alt.X(
                field=COLS["quantity"], type="quantitative",
                axis=alt.Axis(title=None, grid=False),
            ),
            y=alt.Y(
                field="_combo", type="nominal",
                sort=alt.EncodingSortField(field=COLS["quantity"], order="descending"),
                axis=alt.Axis(title=None),
            ),
            color=alt.Color(
                field=COLS["defect"], type="nominal",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(field="_combo", type="nominal", title="Combinação"),
                alt.Tooltip(field=COLS["quantity"], type="quantitative", title="Qtd", format=",d"),
            ],
        )
    )

    text = bars.mark_text(align="left", dx=5, fontSize=11).encode(
        text=alt.Text(field=COLS["quantity"], type="quantitative", format=",d"),
        color=alt.value("#4A5752"),
    )

    return _configure((bars + text).properties(height=h))


# ── Area – defects by date ────────────────────────────────────────────────────

def area_defects_by_date(df: pd.DataFrame) -> alt.Chart:
    base = alt.Chart(df).encode(
        x=alt.X(
            field=COLS["date"], type="temporal",
            axis=alt.Axis(format="%d/%m", title=None, grid=False),
        ),
        y=alt.Y(
            field=COLS["quantity"], type="quantitative",
            axis=alt.Axis(title=None, grid=False),
        ),
        tooltip=[
            alt.Tooltip(field=COLS["date"], type="temporal", title="Data", format="%d/%m/%Y"),
            alt.Tooltip(field=COLS["quantity"], type="quantitative", title="Defeitos", format=",d"),
        ],
    )

    area   = base.mark_area(color="#00B884", opacity=0.12, line=False)
    line   = base.mark_line(color="#00B884", strokeWidth=2.5, interpolate="monotone")
    points = base.mark_circle(color="#00B884", size=55, opacity=1)

    return _configure((area + line + points).properties(height=330))


# ── Area – cost by date ───────────────────────────────────────────────────────

def area_cost_by_date(df: pd.DataFrame) -> alt.Chart:
    base = alt.Chart(df).encode(
        x=alt.X(
            field=COLS["date"], type="temporal",
            axis=alt.Axis(format="%d/%m", title=None, grid=False),
        ),
        y=alt.Y(
            field=COLS["value_brl"], type="quantitative",
            axis=alt.Axis(title=None, grid=False, format="$,.0f"),
        ),
        tooltip=[
            alt.Tooltip(field=COLS["date"], type="temporal", title="Data", format="%d/%m/%Y"),
            alt.Tooltip(field=COLS["value_brl"], type="quantitative", title="Custo (R$)", format=",.2f"),
        ],
    )

    area   = base.mark_area(color="#D85A30", opacity=0.12, line=False)
    line   = base.mark_line(color="#D85A30", strokeWidth=2.5, interpolate="monotone")
    points = base.mark_circle(color="#D85A30", size=55, opacity=1)

    return _configure((area + line + points).properties(height=330))
