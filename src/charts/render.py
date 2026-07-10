"""
Render layer for ECharts specs.

Keeps Streamlit out of `builder.py` (which stays a pure spec factory).
`echart()` receives a spec ``{"opts": ..., "height": ...}`` and draws it.
"""

import streamlit as st
from streamlit_echarts import st_echarts


def echart(spec: dict, key: str) -> None:
    """Render an ECharts spec produced by `src.charts.builder`.

    `key` must be unique on the page (Streamlit widget identity). Any render
    error is contained so a single broken chart never blanks the whole page.
    """
    try:
        st_echarts(
            options=spec["opts"],
            height=f"{spec['height']}px",
            key=key,
        )
    except Exception as exc:  # noqa: BLE001 — chart must never crash the page
        st.warning(f"Não foi possível exibir o gráfico. ({exc})")
