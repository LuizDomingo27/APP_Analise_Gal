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
    "primary":       "#534AB7",
    "primary_light": "#7F77DD",
    "teal":          "#1D9E75",
    "red":           "#E24B4A",
    "blue":          "#378ADD",
    "coral":         "#D85A30",
    "amber":         "#EF9F27",
    "gray":          "#888780",
    "green":         "#639922",
    "text_primary":  "#E8E8FF",
    "text_muted":    "#9898BB",
    "text_subtle":   "#6868AA",
    "border":        "rgba(255,255,255,0.07)",
}

COLOR_SEQUENCE = [
    "#534AB7", "#1D9E75", "#E24B4A", "#378ADD",
    "#D85A30", "#EF9F27", "#7F77DD", "#639922",
    "#888780", "#0F6E56",
]

DEFECT_COLORS = {
    "PONTO ESTOURADO": "#E24B4A",
    "SEM ARREMATE":    "#378ADD",
    "ESGARÇANDO":      "#EF9F27",
    "TAMANHO ERRADO":  "#888780",
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
    "font":          {"family": "Inter, sans-serif", "color": "#9898BB", "size": 12},
    "margin":        {"t": 30, "b": 20, "l": 10, "r": 24},
    "showlegend":    False,
    "hoverlabel":    {"bgcolor": "#1E1E40", "bordercolor": "#534AB7", "font_color": "#E8E8FF"},
}

AXIS_X = {
    "gridcolor":   "rgba(255,255,255,0.05)",
    "linecolor":   "rgba(255,255,255,0.08)",
    "tickcolor":   "rgba(0,0,0,0)",
    "tickfont":    {"color": "#9898BB", "size": 11},
    "zerolinecolor": "rgba(255,255,255,0.08)",
}

AXIS_Y = {
    "gridcolor":   "rgba(255,255,255,0.05)",
    "linecolor":   "rgba(255,255,255,0.08)",
    "tickcolor":   "rgba(0,0,0,0)",
    "tickfont":    {"color": "#9898BB", "size": 11},
    "zerolinecolor": "rgba(255,255,255,0.08)",
    "showgrid":    False,
}
