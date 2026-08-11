"""
Metrics UI layer.
Renders KPI cards and the automatic insights strip.
Receives a DataProcessor, returns nothing (side effects only).
"""

import logging

import streamlit as st
from src.data.processor import DataProcessor
from src.config.theme import accent_alpha, accent_color

logger = logging.getLogger(__name__)


# ── KPI cards ─────────────────────────────────────────────────────────────────

def render_metrics(processor: DataProcessor) -> None:
    # ── Paleta do card ────────────────────────────────────────────────────────
    _NV  = "var(--ag-primary)"          # borda superior / glow
    _NVB = "var(--ag-text-primary)"     # valor principal
    _NVL = "var(--ag-text-primary)"     # label
    _NVS = "var(--ag-text-muted)"       # sublabel
    _BG1 = "var(--ag-bg-surface-alt)"   # fundo do card (topo)
    _BG2 = "var(--ag-bg-surface)"       # fundo do card (base)

    cols = st.columns(5)
    cards = [
        ("✦", "Total de Defeitos",  f"{processor.total_defects():,}",       "peças"),
        ("✦", "Custo de Remonte",   f"R$ {processor.total_cost():,.2f}",     "custo total"),
        ("✦", "Min. Retrabalho",    f"{processor.total_minutes():,.0f}",      "minutos gerados"),
        ("✦", "Fornecedores",       str(processor.unique_suppliers()),         "com ocorrências"),
        ("✦", "Ordens Analisadas",  str(processor.unique_orders()),            "ordens únicas"),
    ]

    card_style = f"""
        background: linear-gradient(160deg, {_BG1} 0%, {_BG2} 100%);
        border: 1px solid rgba(var(--ag-primary-bright-rgb),0.32);
        border-top: 2px solid {_NV};
        border-radius: 12px;
        padding: 1.1rem 1.2rem 1rem;
        box-shadow: 0 0 22px rgba(var(--ag-primary-bright-rgb),0.13),
                    0 2px 8px rgba(var(--ag-shadow-rgb),0.35);
        position: relative; overflow: hidden;
    """

    for col, (icon, label, value, sub) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div style="{card_style}">
                    <div style="
                        position:absolute;top:-18px;right:-18px;
                        width:64px;height:64px;border-radius:50%;
                        background:radial-gradient(circle, rgba(var(--ag-primary-bright-rgb),0.22) 0%, transparent 70%);
                        pointer-events:none;
                    "></div>
                    <div style="font-size:10px;color:{_NVL};
                                text-transform:uppercase;letter-spacing:0.9px;
                                margin-bottom:8px;font-weight:600">
                        <span style="color:{_NV};margin-right:5px">{icon}</span>{label}
                    </div>
                    <div style="font-size:23px;font-weight:700;
                                color:{_NVB};line-height:1.15;
                                letter-spacing:-0.5px">
                        {value}
                    </div>
                    <div style="font-size:11px;color:{_NVS};
                                margin-top:5px;letter-spacing:0.2px">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ── Comparativo mensal (mês vigente × mês anterior) ───────────────────────────

def _delta_badge(
    delta: float, pct: float | None, *, is_money: bool, has_previous: bool = True
) -> str:
    """Badge de variação: ▲ sobe (ruim, vermelho) / ▼ cai (bom, verde) / → estável.

    Vale para as duas métricas do card (peças com defeito e custo de remonte):
    em ambas, subir é piorar — daí a cor de perigo no ▲.

    Sem mês anterior no recorte não existe variação: o badge vira um traço
    neutro, porque um "▲ 320" ali seria lido como alta de 320 peças sobre um
    mês que simplesmente não está na tela.
    """
    if not has_previous or (pct is None and not delta):
        return (
            '<span style="font-size:12px;font-weight:600;color:var(--ag-text-subtle)">—</span>'
        )
    if delta > 0:
        color, arrow = "var(--ag-danger)", "▲"
    elif delta < 0:
        color, arrow = "var(--ag-primary-dark)", "▼"
    else:
        color, arrow = "var(--ag-text-subtle)", "→"

    if pct is None:
        # Mês anterior zerado: o percentual não existe, mas o valor absoluto sim.
        texto = f"R$ {abs(delta):,.2f}" if is_money else f"{abs(int(delta)):,}"
    else:
        texto = f"{abs(pct):,.1f}%"
    return (
        f'<span style="font-size:12.5px;font-weight:700;color:{color};'
        f'background:rgba(var(--ag-primary-bright-rgb),0.10);'
        f'border-radius:6px;padding:2px 8px;white-space:nowrap">{arrow} {texto}</span>'
    )


def _comparison_card(
    icon: str, label: str, month_label: str, value: str,
    previous_label: str, previous_value: str,
    delta_html: str, delta_text: str, has_previous: bool,
) -> str:
    sub = (
        f"{previous_label}: {previous_value} &nbsp;·&nbsp; {delta_text}"
        if has_previous
        else "Sem mês anterior no recorte — amplie o período para comparar."
    )
    return f"""
    <div style="
        background: linear-gradient(160deg, var(--ag-bg-surface-alt) 0%, var(--ag-bg-surface) 100%);
        border: 1px solid rgba(var(--ag-primary-bright-rgb),0.32);
        border-top: 2px solid var(--ag-primary);
        border-radius: 12px;
        padding: 1rem 1.2rem 0.9rem;
        box-shadow: 0 0 22px rgba(var(--ag-primary-bright-rgb),0.13),
                    0 2px 8px rgba(var(--ag-shadow-rgb),0.35);
    ">
        <div style="font-size:10px;color:var(--ag-text-primary);
                    text-transform:uppercase;letter-spacing:0.9px;
                    margin-bottom:8px;font-weight:600">
            <span style="color:var(--ag-primary);margin-right:5px">{icon}</span>{label}
            <span style="color:var(--ag-text-muted);font-weight:500"> · {month_label}</span>
        </div>
        <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
            <span style="font-size:23px;font-weight:700;color:var(--ag-text-primary);
                         line-height:1.15;letter-spacing:-0.5px">{value}</span>
            {delta_html}
        </div>
        <div style="font-size:11px;color:var(--ag-text-muted);margin-top:6px;
                    letter-spacing:0.2px">{sub}</div>
    </div>
    """


def render_month_comparison(processor: DataProcessor) -> None:
    """Card comparativo entre o mês vigente e o mês anterior (peças e valor).

    Fronteira defensiva: qualquer falha no cálculo degrada apenas este bloco —
    os KPIs e os gráficos da página continuam de pé.
    """
    try:
        data = processor.month_over_month()
    except Exception:  # noqa: BLE001 — fronteira: o comparativo nunca derruba a página
        logger.exception("Falha ao calcular o comparativo mensal")
        return

    if not data["has_current"]:
        return

    st.markdown(
        f'<p style="font-size:11px;text-transform:uppercase;letter-spacing:1px;'
        f'color:var(--ag-text-muted);margin:0 0 8px">📊 Comparativo mensal — '
        f'{data["current_label"]} vs {data["previous_label"]}</p>',
        unsafe_allow_html=True,
    )

    pieces_delta = data["pieces_delta"]
    value_delta  = data["value_delta"]

    cards = [
        _comparison_card(
            "🧵", "Peças com defeito", data["current_label"],
            f'{data["current_pieces"]:,}',
            data["previous_label"], f'{data["previous_pieces"]:,}',
            _delta_badge(
                pieces_delta, data["pieces_pct"],
                is_money=False, has_previous=data["has_previous"],
            ),
            f'{pieces_delta:+,} peça(s)',
            data["has_previous"],
        ),
        _comparison_card(
            "💰", "Custo de remonte", data["current_label"],
            f'R$ {data["current_value"]:,.2f}',
            data["previous_label"], f'R$ {data["previous_value"]:,.2f}',
            _delta_badge(
                value_delta, data["value_pct"],
                is_money=True, has_previous=data["has_previous"],
            ),
            f'{"+" if value_delta >= 0 else "-"}R$ {abs(value_delta):,.2f}',
            data["has_previous"],
        ),
    ]

    for col, card_html in zip(st.columns(2), cards):
        with col:
            st.markdown(card_html, unsafe_allow_html=True)


# ── Auto-insights strip ───────────────────────────────────────────────────────

def render_insights(processor: DataProcessor) -> None:
    sup_name, sup_qty   = processor.top_supplier_by_quantity()
    cost_name, cost_val = processor.top_supplier_by_cost()
    def_name, def_qty, def_pct = processor.top_defect()

    cols = st.columns(3)
    items = [
        (
            cols[0],
            "⚠️ MAIOR VOLUME",
            sup_name,
            f"{sup_qty:,} peças com defeito",
            "danger",
        ),
        (
            cols[1],
            "💰 MAIOR CUSTO",
            cost_name,
            f"R$ {cost_val:,.2f} em retrabalho",
            "accent-coral",
        ),
        (
            cols[2],
            "🔍 DEFEITO DOMINANTE",
            def_name,
            f"{def_qty:,} ocorrências — {def_pct:.1f}% do total",
            "primary",
        ),
    ]
    # `accent` é o nome de um token, não uma cor: o card usa a mesma cor sólida e
    # a 5%, e derivá-las do nome evita o `{color}0D` de antes — concatenar sufixo
    # de alpha só funciona com hex literal e quebra em silêncio com var().
    for col, badge, title, sub, accent in items:
        color = accent_color(accent)
        with col:
            st.markdown(
                f"""
                <div style="
                    background:{accent_alpha(accent, 0.051)};
                    border-left:3px solid {color};
                    border-radius:8px;
                    padding:0.85rem 1rem;
                ">
                    <div style="font-size:10px;color:{color};
                                text-transform:uppercase;letter-spacing:0.6px;margin-bottom:5px">
                        {badge}
                    </div>
                    <div style="font-size:13px;font-weight:600;color:var(--ag-text-primary);
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        {title}
                    </div>
                    <div style="font-size:12px;color:var(--ag-text-muted);margin-top:3px">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
