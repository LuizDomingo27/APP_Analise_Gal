# -*- coding: utf-8 -*-
"""
CSS da página de Performance.

Duas diferenças deliberadas em relação ao CSS do app original (APP_PERFOR):

1. NADA de esconder cabeçalho ou sidebar. O original abria com
   `[data-testid="stHeader"] { display:none }` e o mesmo para a sidebar, porque
   lá ele era o app inteiro e desenhava a própria navbar. Aqui isso apagaria a
   navegação do Gal — a navbar do topo E o botão que abre a sidebar no celular,
   que abaixo de 768px é a ÚNICA navegação disponível. Quem manda no cabeçalho é
   o roteador (app.py).

2. Classes prefixadas com `perf-` e cores por `var(--ag-*)`. O original estilizava
   seletores globais (`.stButton > button`, `[data-baseweb="select"]`, `.stTabs`),
   o que vazaria para todas as outras páginas — o CSS do Streamlit é global, não
   tem escopo por página. Aqui só existem classes próprias desta página; a
   aparência dos widgets continua vindo do CSS global do app.py.
"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
/* ── Cartões de KPI ─────────────────────────────────────────────────────── */
.perf-kpi {
    min-height: 132px;
    background: var(--ag-bg-surface);
    border: 1px solid var(--ag-border-hairline);
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 6px 20px rgba(var(--ag-shadow-rgb), .045);
}
.perf-kpi.danger { border-color: rgba(var(--ag-danger-rgb), .35); }
.perf-kpi-label {
    color: var(--ag-text-muted);
    font-size: .68rem;
    letter-spacing: .08em;
    text-transform: uppercase;
    font-weight: 700;
}
.perf-kpi-value {
    color: var(--ag-text-primary);
    font-size: clamp(1.4rem, 2.2vw, 1.95rem);
    line-height: 1.12;
    font-weight: 800;
    margin: 9px 0 7px;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
}
.perf-kpi-value.cyan { color: var(--ag-primary-dark); }
.perf-kpi-value.danger { color: var(--ag-danger); }
.perf-kpi-detail { color: var(--ag-text-muted); font-size: .76rem; line-height: 1.35; }

/* ── Títulos de seção ───────────────────────────────────────────────────── */
.perf-panel-title {
    color: var(--ag-primary-dark);
    font-size: .74rem;
    letter-spacing: .11em;
    font-weight: 800;
    text-transform: uppercase;
    margin: 10px 0 12px;
}

/* ── Cartões de extremo (melhor / pior fornecedor) ──────────────────────── */
.perf-rank {
    background: var(--ag-bg-surface);
    border: 1px solid var(--ag-border-hairline);
    border-radius: 14px;
    padding: 16px 18px;
    min-height: 112px;
    box-shadow: 0 6px 20px rgba(var(--ag-shadow-rgb), .04);
}
.perf-rank-name {
    color: var(--ag-text-primary);
    font-weight: 700;
    font-size: .95rem;
    margin: 7px 0;
    min-height: 42px;
}
.perf-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 99px;
    font-size: .7rem;
    font-weight: 800;
}
.perf-badge.bad {
    background: rgba(var(--ag-danger-rgb), .10);
    color: var(--ag-danger);
    border: 1px solid rgba(var(--ag-danger-rgb), .30);
}
.perf-badge.good {
    background: rgba(var(--ag-primary-bright-rgb), .14);
    color: var(--ag-primary-dark);
    border: 1px solid rgba(var(--ag-primary-rgb), .30);
}

/* ── Aviso de qualidade de dados ────────────────────────────────────────── */
.perf-note {
    background: rgba(var(--ag-warning-rgb), .10);
    border-left: 3px solid var(--ag-warning);
    border-radius: 7px;
    padding: 10px 12px;
    color: var(--ag-text-primary);
    font-size: .8rem;
}

/* ── Tabela ─────────────────────────────────────────────────────────────── */
.perf-table-wrap {
    overflow: auto;
    max-height: 640px;
    border: 1px solid var(--ag-border-hairline);
    border-radius: 12px;
    background: var(--ag-bg-surface);
}
.perf-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: .78rem;
}
.perf-table thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--ag-bg-surface-alt);
    color: var(--ag-primary-dark);
    text-align: left;
    text-transform: uppercase;
    letter-spacing: .055em;
    font-size: .64rem;
    padding: 12px;
    border-bottom: 1px solid var(--ag-border-hairline);
    white-space: nowrap;
}
.perf-table tbody td {
    color: var(--ag-text-primary);
    padding: 11px 12px;
    border-bottom: 1px solid var(--ag-border-hairline);
    vertical-align: middle;
}
.perf-table tbody tr:hover td { background: var(--ag-bg-surface-alt); }
.perf-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.perf-table .bad-text { color: var(--ag-danger); font-weight: 700; }
.perf-table .good-text { color: var(--ag-primary-dark); font-weight: 700; }

/* ── Caixa de exportação do ranking ─────────────────────────────────────── */
.st-key-perf_export {
    margin-top: 1.3rem;
    padding: 16px 18px 18px;
    background: var(--ag-bg-surface);
    border: 1px solid var(--ag-border-hairline);
    border-radius: 13px;
    box-shadow: 0 6px 20px rgba(var(--ag-shadow-rgb), .04);
}
.perf-export-heading { display: flex; flex-direction: column; gap: 3px; margin-bottom: 4px; }
.perf-export-heading strong { color: var(--ag-text-primary); font-size: .92rem; }
.perf-export-heading span { color: var(--ag-text-muted); font-size: .78rem; }
.st-key-perf_export .stDownloadButton > button { min-height: 42px; }

/* ── Barra de filtros ───────────────────────────────────────────────────── */
.st-key-perf_filters [data-testid="stPopover"] > button { min-height: 40px; width: 100%; }

@media (max-width: 760px) {
    .perf-kpi { min-height: 112px; }
    .perf-kpi-value { white-space: normal; }
}
@media print {
    .perf-table-wrap { max-height: none; overflow: visible; }
}
</style>
"""


def apply_performance_theme() -> None:
    """Injeta o CSS da página. Idempotente — pode ser chamado a cada rerun."""
    st.markdown(CSS, unsafe_allow_html=True)
