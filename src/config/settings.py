"""
Central configuration: colors, column names, ECharts layout defaults.
"""

from pathlib import Path

# ── Dataset paths ─────────────────────────────────────────────────────────────
_ROOT_DIR    = Path(__file__).resolve().parents[2]
DATASET_DIR  = _ROOT_DIR / "dataset"

PAGE_CONFIG = {
    "page_title": "Análise Remontes",
    "page_icon": "⌚",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# ── Palette ──────────────────────────────────────────────────────────────────
COLORS = {
    "primary":       "#00B884",
    "primary_light": "#5FF6C6",
    "teal":          "#00E5A0",
    "red":           "#E24B4A",
    "blue":          "#0EA5C7",
    "coral":         "#D85A30",
    "amber":         "#EF9F27",
    "gray":          "#7C8985",
    "green":         "#00B884",
    "text_primary":  "#0D1B17",
    "text_muted":    "#4A5752",
    "text_subtle":   "#7C8985",
    "border":        "rgba(0,0,0,0.07)",
}

COLOR_SEQUENCE = [
    "#00E5A0",
    "#00B884",
    "#0EA5C7",
    "#5FF6C6",
    "#3DDC97",
    "#F0B840",
    "#7C8985",
    "#E24B4A",
    "#0F8060",
    "#00805C",
]

DEFECT_COLORS = {
    "PONTO ESTOURADO": "#E24B4A",
    "SEM ARREMATE":    "#0EA5C7",
    "ESGARÇANDO":      "#EF9F27",
    "TAMANHO ERRADO":  "#7C8985",
    "TROCAR":          "#D85A30",
}

# ── Column names (matches the spreadsheet exactly) ────────────────────────────
COLS = {
    "date":         "DATA DE PRODUÇÃO ACABAMENTO",
    "order":        "ORDEM MESTRE",
    "material":     "MATERIAL",
    "supplier":     "FORNECEDOR",
    "quantity":     "QUANTIDADE",
    "location":     "LOCAL",
    "defect":       "REMONTE",
    "real_cut":     "REAL CORTADO",
    "pct_remonte":  "PERCENTUAL DE REMONTE",
    "key":          "CHAVE",
    "process_time": "TEMPO DE PROCESSO",
    "minutes":      "MINUTOS GERADOS",
    "value_brl":    "VALOR DO PROCESSO BRL",
    "status":       "STATUS_COBRANCA",
}

# ── Altair/Vega-Lite theme config ─────────────────────────────────────────────
ALTAIR_AXIS = {
    "labelColor": "#4A5752",
    "labelFontSize": 11,
    "labelFont": "Inter, sans-serif",
    "grid": False,
    "domainColor": "rgba(0,0,0,0.10)",
    "tickColor": "rgba(0,0,0,0)",
    "titleColor": "#4A5752",
}

ALTAIR_CONFIG = {
    "background": "transparent",
    "font": "Inter, sans-serif",
    "axis": ALTAIR_AXIS,
    "view": {"strokeOpacity": 0},
}
