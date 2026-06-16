"""
Central configuration: colors, column names, Plotly layout defaults.
"""

from pathlib import Path

# ── Dataset paths ─────────────────────────────────────────────────────────────
_ROOT_DIR    = Path(__file__).resolve().parents[2]
DATASET_DIR  = _ROOT_DIR / "dataset"
BD_PRINCIPAL = DATASET_DIR / "bd_principal.xlsx"

PAGE_CONFIG = {
    "page_title": "Análise Remontes",
    "page_icon": "🔍",
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

# ── Plotly defaults ───────────────────────────────────────────────────────────
PLOTLY_BASE = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor":  "rgba(0,0,0,0)",
    "font":          {"family": "Inter, sans-serif", "color": "#4A5752", "size": 12},
    "margin":        {"t": 30, "b": 20, "l": 10, "r": 24},
    "showlegend":    False,
    "hoverlabel":    {"bgcolor": "#FFFFFF", "bordercolor": "#00B884", "font_color": "#0D1B17"},
}

AXIS_X = {
    "gridcolor":   "rgba(0,0,0,0.06)",
    "linecolor":   "rgba(0,0,0,0.10)",
    "tickcolor":   "rgba(0,0,0,0)",
    "tickfont":    {"color": "#4A5752", "size": 11},
    "zerolinecolor": "rgba(0,0,0,0.10)",
}

AXIS_Y = {
    "gridcolor":   "rgba(0,0,0,0.06)",
    "linecolor":   "rgba(0,0,0,0.10)",
    "tickcolor":   "rgba(0,0,0,0)",
    "tickfont":    {"color": "#4A5752", "size": 11},
    "zerolinecolor": "rgba(0,0,0,0.10)",
    "showgrid":    False,
}
