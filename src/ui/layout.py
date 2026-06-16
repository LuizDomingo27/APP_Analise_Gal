"""
Layout UI layer.
Organises Plotly charts into page sections using Streamlit columns.
Calls chart builder functions; does not contain chart logic.
Always 2 charts per row.
"""

import base64
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from src.data.processor import DataProcessor
from src.charts import builder
from src.ui.preview import _generate_html
from src.services.exporter import get_xlsx_bytes
from src.config.settings import COLS, COLORS, DEFECT_COLORS


# ── Section heading ───────────────────────────────────────────────────────────

def _section(title: str, icon: str = "📊") -> None:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin:2rem 0 0.7rem">
            <span style="font-size:18px">{icon}</span>
            <span style="font-size:15px;font-weight:600;color:{COLORS['text_primary']}">{title}</span>
            <div style="flex:1;height:1px;background:rgba(0,0,0,0.07);margin-left:6px"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _chart_label(text: str) -> None:
    st.markdown(
        f'<p style="font-size:12px;color:{COLORS["text_muted"]};'
        f'font-weight:500;margin:0 0 4px">{text}</p>',
        unsafe_allow_html=True,
    )


def _defect_legend() -> None:
    items = "".join(
        f'<span style="display:flex;align-items:center;gap:5px;'
        f'font-size:11px;color:{COLORS["text_muted"]}">'
        f'<span style="width:9px;height:9px;border-radius:2px;'
        f'background:{color};display:inline-block"></span>'
        f'{label}</span>'
        for label, color in DEFECT_COLORS.items()
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:6px">{items}</div>',
        unsafe_allow_html=True,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def render_charts(processor: DataProcessor, full_df: pd.DataFrame) -> None:
    _render_distribution(processor)
    _render_temporal(processor)
    _render_suppliers(processor)
    _render_table(processor, full_df)


# ── Section 1: Distribuição de Defeitos ──────────────────────────────────────

def _render_distribution(processor: DataProcessor) -> None:
    _section("Distribuição de Defeitos", "🔍")
    c1, c2 = st.columns(2)

    with c1:
        _chart_label("Tipo de defeito")
        _defect_legend()
        st.plotly_chart(
            builder.donut_defect_type(processor.by_defect_type()),
            use_container_width=True,
        )

    with c2:
        _chart_label("Local do defeito")
        st.plotly_chart(
            builder.bar_location(processor.by_location()),
            use_container_width=True,
        )


# ── Section 2: Evolução Temporal ──────────────────────────────────────────────

def _render_temporal(processor: DataProcessor) -> None:
    _section("Evolução Temporal", "📅")
    c1, c2 = st.columns(2)

    with c1:
        _chart_label("Defeitos por dia")
        st.plotly_chart(
            builder.area_defects_by_date(processor.by_date()),
            use_container_width=True,
        )

    with c2:
        _chart_label("Custo de remonte por dia (R$)")
        st.plotly_chart(
            builder.area_cost_by_date(processor.by_date_cost()),
            use_container_width=True,
        )


# ── Section 3: Análise por Fornecedor (2 linhas × 2 colunas) ─────────────────

def _render_suppliers(processor: DataProcessor) -> None:
    _section("Análise por Fornecedor", "🏭")

    # Linha 1: quantidade e custo
    c1, c2 = st.columns(2)
    with c1:
        _chart_label("Top 10 — quantidade de defeitos")
        st.plotly_chart(
            builder.bar_supplier_quantity(processor.by_supplier_quantity(10)),
            use_container_width=True,
        )
    with c2:
        _chart_label("Top 10 — custo de remonte (R$)")
        st.plotly_chart(
            builder.bar_supplier_cost(processor.by_supplier_cost(10)),
            use_container_width=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Linha 2: taxa de remonte e combinações
    c3, c4 = st.columns(2)
    with c3:
        _chart_label("Top 10 — taxa de remonte (%)")
        st.plotly_chart(
            builder.bar_supplier_rate(processor.by_supplier_rate(10)),
            use_container_width=True,
        )
    with c4:
        _chart_label("Top 12 — combinações Local × Defeito")
        _defect_legend()
        st.plotly_chart(
            builder.bar_key_combinations(processor.by_key(12)),
            use_container_width=True,
        )


# ── Section 4: Tabela de dados detalhados ─────────────────────────────────────

def _render_table(processor: DataProcessor, full_df: pd.DataFrame) -> None:

    _section("Dados Detalhados", "📋")

    # ── Gera conteúdo em memória ───────────────────────────────────────────────
    html_page = _generate_html(processor.df, full_df)
    html_b64  = base64.b64encode(html_page.encode("utf-8")).decode()

    xlsx_bytes = get_xlsx_bytes(processor.df)
    xlsx_b64   = base64.b64encode(xlsx_bytes).decode()
    save_href  = (
        "data:application/vnd.openxmlformats-officedocument"
        f".spreadsheetml.sheet;base64,{xlsx_b64}"
    )

    # ── Barra de ação via components.html (permite JS) ─────────────────────────
    n = len(processor.df)
    components.html(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 4px 2px 8px;
  }}
  .action-bar {{
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; flex-wrap: wrap;
  }}
  .info-text {{
    font-size: 12px; color: #4A5752;
    flex: 1; min-width: 200px;
  }}
  .action-btns {{
    display: flex; align-items: center; gap: 10px; flex-shrink: 0;
  }}
  .abtn {{
    display: inline-flex; align-items: center; gap: 8px;
    padding: 9px 20px; border-radius: 10px; cursor: pointer;
    font-size: 12.5px; font-weight: 600; letter-spacing: 0.4px;
    white-space: nowrap; text-decoration: none;
    transition: background 0.2s, box-shadow 0.2s, transform 0.15s;
    line-height: 1; color: #0D1B17;
  }}
  .abtn-print {{
    background: #F2F7F5;
    border: 1px solid rgba(0,229,160,0.50);
    box-shadow: 0 0 14px rgba(0,229,160,0.12);
  }}
  .abtn-print:hover {{
    background: rgba(0,229,160,0.20);
    border-color: rgba(0,229,160,0.80);
    box-shadow: 0 0 20px rgba(0,229,160,0.28);
    transform: translateY(-1px);
  }}
  .abtn-save {{
    background: rgba(0,229,160,0.22);
    border: 1px solid rgba(0,229,160,0.55);
    box-shadow: 0 0 14px rgba(0,229,160,0.18);
    color: #0D1B17;
  }}
  .abtn-save:hover {{
    background: rgba(0,229,160,0.35);
    border-color:#0D1B17;
    box-shadow: 0 0 24px rgba(0,229,160,0.38);
    transform: translateY(-1px);
  }}
  .abtn:active {{ transform: translateY(0); }}
  .abtn-icon {{ font-size: 14px; opacity: 0.85; }}
</style>
</head>
<body>
<div class="action-bar">
  <span class="info-text">
    ✦ {n:,} registros filtrados · abra a prévia de impressão ou exporte os dados agrupados por fornecedor.
  </span>
  <div class="action-btns">
    <button class="abtn abtn-print" onclick="openPreview()">
      <span class=""></span> Prévia / Imprimir PDF
    </button>
    <a class="abtn abtn-save" href="{save_href}" download="defeitos_fornecedor.xlsx">
      <span class=""</span> Salvar por Fornecedor
    </a>
  </div>
</div>

<script>
  const _HTML_B64 = "{html_b64}";

  function openPreview() {{
    try {{
      const bytes = Uint8Array.from(atob(_HTML_B64), c => c.charCodeAt(0));
      const html  = new TextDecoder("utf-8").decode(bytes);
      const win   = window.open("", "_blank");
      if (win) {{
        win.document.open();
        win.document.write(html);
        win.document.close();
      }} else {{
        const blob = new Blob([html], {{ type: "text/html;charset=utf-8" }});
        window.open(URL.createObjectURL(blob), "_blank");
      }}
    }} catch (err) {{
      console.error("Erro ao abrir prévia:", err);
      alert("Não foi possível abrir a prévia. Permita popups para este site.");
    }}
  }}
</script>
</body>
</html>""",
        height=58,
        scrolling=False,
    )

    # ── Tabela inline ─────────────────────────────────────────────────────────
    with st.expander(f"Expandir tabela ({n:,} registros)", expanded=False):
        display = processor.df.copy()
        display[COLS["date"]]        = display[COLS["date"]].dt.strftime("%d/%m/%Y")
        display[COLS["pct_remonte"]] = (display[COLS["pct_remonte"]] * 100).round(2)
        display[COLS["value_brl"]]   = display[COLS["value_brl"]].round(2)
        display[COLS["minutes"]]     = display[COLS["minutes"]].round(2)

        headers = [
            "Data", "Ordem", "Fornecedor", "Local", "Defeito",
            "Qtd", "Real Cortado", "% Remonte", "Minutos", "Valor (R$)",
        ]
        col_keys = [
            COLS["date"], COLS["order"], COLS["supplier"], COLS["location"], COLS["defect"],
            COLS["quantity"], COLS["real_cut"], COLS["pct_remonte"], COLS["minutes"], COLS["value_brl"],
        ]

        thr_val  = float(display[COLS["value_brl"]].quantile(0.75))
        thr_qty  = float(display[COLS["quantity"]].quantile(0.75))
        thr_mins = float(display[COLS["minutes"]].quantile(0.75))

        TH = (
            "padding:11px 14px;text-align:center;color:#0D1B17;font-weight:600;"
            "font-size:10px;text-transform:uppercase;letter-spacing:0.9px;"
            "background:#FFFFFF;border-bottom:1px solid rgba(0,229,160,0.35);"
            "white-space:nowrap;position:sticky;top:0;z-index:1;"
        )
        TH_L = TH + "text-align:left;"

        head_html = "".join(
            f'<th style="{TH_L if h == "Fornecedor" else TH}">✦ {h}</th>'
            for h in headers
        )

        rows_html = ""
        for i, (_, row) in enumerate(display.iterrows()):
            row_bg = (
                "background:rgba(0,229,160,0.07);"
                if i % 2 == 1
                else "background:#F2F7F5;"
            )
            cells = ""
            for key in col_keys:
                val = row[key]
                is_left = key == COLS["supplier"]
                align   = "text-align:left;" if is_left else "text-align:center;"
                base_td = (
                    f"padding:9px 14px;font-size:12.5px;color:#0D1B17;"
                    f"border-bottom:1px solid rgba(0,229,160,0.12);"
                    f"{align}{row_bg}"
                )

                if key == COLS["value_brl"]:
                    fval     = float(val)
                    badge_bg = "rgba(0,229,160,0.28)" if fval > thr_val else "rgba(0,229,160,0.10)"
                    badge_cl = "#0D1B17" if fval > thr_val else "#4A5752"
                    cells += (
                        f'<td style="{base_td}">'
                        f'<span style="background:{badge_bg};color:{badge_cl};'
                        f'padding:3px 9px;border-radius:6px;'
                        f'font-size:12px;font-weight:600;white-space:nowrap;">'
                        f'R$ {fval:,.2f}</span></td>'
                    )
                elif key == COLS["pct_remonte"]:
                    cells += f'<td style="{base_td};color:#4A5752;">{float(val):.2f}%</td>'
                elif key == COLS["quantity"]:
                    ival   = int(val)
                    weight = "font-weight:600;" if ival > thr_qty else ""
                    cells += f'<td style="{base_td}{weight}">{ival:,}</td>'
                elif key == COLS["minutes"]:
                    fval   = float(val)
                    weight = "font-weight:600;" if fval > thr_mins else ""
                    cells += f'<td style="{base_td}{weight}">{fval:,.2f}</td>'
                elif key == COLS["real_cut"]:
                    cells += f'<td style="{base_td}">{int(val):,}</td>'
                elif key == COLS["order"]:
                    cells += f'<td style="{base_td};color:#4A5752;">{int(val)}</td>'
                elif key == COLS["date"]:
                    cells += f'<td style="{base_td};color:#4A5752;">{val}</td>'
                else:
                    cells += f'<td style="{base_td}">{val}</td>'

            rows_html += f"<tr>{cells}</tr>"

        table_html = f"""
        <style>
          .nv-table-wrap::-webkit-scrollbar {{ width:6px; height:6px; }}
          .nv-table-wrap::-webkit-scrollbar-track {{ background:#FFFFFF; border-radius:3px; }}
          .nv-table-wrap::-webkit-scrollbar-thumb {{ background:rgba(0,229,160,0.45); border-radius:3px; }}
          .nv-table-wrap::-webkit-scrollbar-thumb:hover {{ background:rgba(0,229,160,0.70); }}
          .nv-table-wrap tr:hover td {{ background:rgba(0,229,160,0.14)!important; transition:background 0.15s; }}
        </style>
        <div class="nv-table-wrap" style="
            max-height:460px; overflow:auto; border-radius:12px;
            border:1px solid rgba(0,229,160,0.32);
            border-top:2px solid #00B884;
            background:#F2F7F5;
            box-shadow:0 0 22px rgba(0,229,160,0.10);
        ">
          <table style="width:100%;border-collapse:collapse;min-width:980px;">
            <thead><tr>{head_html}</tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)
