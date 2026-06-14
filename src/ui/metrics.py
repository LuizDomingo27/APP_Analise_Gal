"""
Metrics UI layer.
Renders KPI cards and the automatic insights strip.
Receives a DataProcessor, returns nothing (side effects only).
"""

import streamlit as st
from src.data.processor import DataProcessor
from src.config.settings import COLORS


# ── KPI cards ─────────────────────────────────────────────────────────────────

def render_metrics(processor: DataProcessor) -> None:
    # ── paleta neon-roxo unificada ────────────────────────────────────────────
    _NV  = "#7B5EA7"   # neon violet — borda superior / glow
    _NVB = "#F8F6FF"   # branco neve — valor principal
    _NVL = "#EDE8FF"   # branco neve suave — label
    _NVS = "#C8C0F0"   # branco neve tênue — sublabel
    _BG1 = "#14112A"   # fundo escuro do card (topo)
    _BG2 = "#0D0B1F"   # fundo escuro do card (base)

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
        border: 1px solid rgba(123,94,167,0.32);
        border-top: 2px solid {_NV};
        border-radius: 12px;
        padding: 1.1rem 1.2rem 1rem;
        box-shadow: 0 0 22px rgba(123,94,167,0.13),
                    0 2px 8px rgba(0,0,0,0.35);
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
                        background:radial-gradient(circle, rgba(123,94,167,0.22) 0%, transparent 70%);
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
            COLORS["red"],
        ),
        (
            cols[1],
            "💰 MAIOR CUSTO",
            cost_name,
            f"R$ {cost_val:,.2f} em retrabalho",
            COLORS["coral"],
        ),
        (
            cols[2],
            "🔍 DEFEITO DOMINANTE",
            def_name,
            f"{def_qty:,} ocorrências — {def_pct:.1f}% do total",
            COLORS["primary"],
        ),
    ]
    for col, badge, title, sub, color in items:
        with col:
            st.markdown(
                f"""
                <div style="
                    background:{color}0D;
                    border-left:3px solid {color};
                    border-radius:8px;
                    padding:0.85rem 1rem;
                ">
                    <div style="font-size:10px;color:{color};
                                text-transform:uppercase;letter-spacing:0.6px;margin-bottom:5px">
                        {badge}
                    </div>
                    <div style="font-size:13px;font-weight:600;color:{COLORS['text_primary']};
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        {title}
                    </div>
                    <div style="font-size:12px;color:{COLORS['text_muted']};margin-top:3px">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
