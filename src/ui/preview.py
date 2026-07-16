"""
Preview page generator — tema clean light.
Fundo branco, acentos #00B884 / #00805C, warmth #F2F7F5.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo
import pandas as pd
from src.config.settings import COLS

# Servidores de hospedagem (ex.: Streamlit Cloud) costumam rodar em horário
# americano/UTC — os relatórios impressos/pré-visualizados devem sempre
# mostrar o horário local do Brasil, independente do fuso do servidor.
_TZ_BR = ZoneInfo("America/Sao_Paulo")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_cards(fdf: pd.DataFrame, tdf: pd.DataFrame) -> list[dict]:
    f_ord = fdf[COLS["order"]].nunique()
    f_rem = len(fdf)
    f_pcs = int(fdf[COLS["quantity"]].sum())
    f_min = float(fdf[COLS["minutes"]].sum())
    f_Valor = float(fdf[COLS["value_brl"]].sum())
    
    t_ord = tdf[COLS["order"]].nunique()
    t_rem = len(tdf)
    t_pcs = int(tdf[COLS["quantity"]].sum())
    t_min = float(tdf[COLS["minutes"]].sum())
    t_Valor = float(tdf[COLS["value_brl"]].sum())
    def pct(a, b):
        return f"{a / b * 100:.1f}%" if b else "0.0%"

    return [
        {"icon": "📋", "label": "Total de Ordens",
         "value": f"{f_ord:,}", "detail": f"de {t_ord:,} ordens", "pct": pct(f_ord, t_ord)},
        {"icon": "🔁", "label": "Total de Remontes",
         "value": f"{f_rem:,}", "detail": f"de {t_rem:,} registros", "pct": pct(f_rem, t_rem)},
        {"icon": "🧵", "label": "Total de Peças",
         "value": f"{f_pcs:,}", "detail": f"de {t_pcs:,} peças", "pct": pct(f_pcs, t_pcs)},
        {"icon": "⏱️", "label": "Total de Minutos",
         "value": f"{f_min:,.0f}", "detail": f"de {t_min:,.0f} min", "pct": pct(f_min, t_min)},
        {"icon": "💰", "label": "Total em Valor",
         "value": f"R$ {f_Valor:,.2f}", "detail": f"de R$ {t_Valor:,.2f}", "pct": pct(f_Valor, t_Valor)},
    ]


def _get_thresholds(tdf: pd.DataFrame) -> dict:
    return {
        "qty":  tdf[COLS["quantity"]].quantile(0.75),
        "vbrl": tdf[COLS["value_brl"]].quantile(0.75),
        "mins": tdf[COLS["minutes"]].quantile(0.75),
    }


def _b(formatted: str, raw_val: float, threshold: float) -> str:
    return f"<strong class='hi'>{formatted}</strong>" if raw_val > threshold else formatted


def _fmt_int(value, sep: bool = True) -> str:
    """
    Formata ORDEM MESTRE / REAL CORTADO / Qtd para exibição.

    `_cast_types` (src/data/loader.py) não converte ORDEM MESTRE nem REAL
    CORTADO para numérico — elas chegam como `object` e podem conter texto
    ("OM-100"), vazio ou NaN. Um `int(value)` direto levanta ValueError e
    derruba o relatório inteiro por causa de uma única célula. Aqui, o valor
    numérico é formatado (com separador de milhar quando `sep`), e qualquer
    outra coisa é exibida como o texto original.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        texto = str(value).strip()
        return texto or "—"
    return f"{n:,}" if sep else f"{n}"


def _build_rows(fdf: pd.DataFrame, thr: dict) -> str:
    d = fdf.copy()
    d[COLS["date"]]      = d[COLS["date"]].dt.strftime("%d/%m/%Y")
    d[COLS["value_brl"]] = d[COLS["value_brl"]].round(2)
    d[COLS["minutes"]]   = d[COLS["minutes"]].round(2)

    def _make_row(row):
        qty  = int(row[COLS["quantity"]])
        vbrl = float(row[COLS["value_brl"]])
        mins = float(row[COLS["minutes"]])
        return (
            "<tr>"
            f"<td class='tdl'>{row[COLS['supplier']]}</td>"
            f"<td>{_fmt_int(row[COLS['order']])}</td>"
            f"<td>{row[COLS['date']]}</td>"
            f"<td>{_b(f'{qty:,}', qty, thr['qty'])}</td>"
            f"<td class='tdl'>{row[COLS['defect']]}</td>"
            f"<td>{_fmt_int(row[COLS['real_cut']])}</td>"
            f"<td>{_b(f'{mins:,.2f}', mins, thr['mins'])}</td>"
            f"<td>{_b(f'R$ {vbrl:,.2f}', vbrl, thr['vbrl'])}</td>"
            "</tr>"
        )

    return "".join(_make_row(row) for _, row in d.iterrows())


# ── Shared CSS Template for All Reports ────────────────────────────────────────

_SHARED_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
  background:#FFFFFF;
  color:#0D1B17;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Inter',sans-serif;
  padding:2rem 2.8rem;font-size:14px;line-height:1.55;
  -webkit-font-smoothing:antialiased;
}

/* ── Header ── */
.header{
  display:flex;align-items:flex-start;justify-content:space-between;
  gap:1.5rem;padding-bottom:1.2rem;
  border-bottom:2px solid #00B884;margin-bottom:2rem;
}
.htitle{font-size:20px;font-weight:700;color:#00805C;letter-spacing:-0.3px}
.htitle span{color:#0D1B17}
.hsub{font-size:12px;color:#0D1B17;margin-top:4px}
.hbadge{
  font-size:11px;background:#F2F7F5;color:#00805C;
  border:1px solid #00B884;border-radius:20px;
  padding:3px 12px;white-space:nowrap;align-self:flex-start;font-weight:600;
}
.hright{display:flex;flex-direction:column;align-items:flex-end;gap:10px}
.hts{font-size:11px;color:#0D1B17}

/* ── PDF Button ── */
.pdf-btn{
  display:inline-flex;align-items:center;gap:7px;
  background:#00805C;color:#FFFFFF;
  border:none;padding:9px 20px;border-radius:7px;cursor:pointer;
  font-size:13px;font-weight:600;letter-spacing:0.2px;
  box-shadow:0 2px 8px rgba(0,229,160,0.22);
  transition:background 0.2s,box-shadow 0.2s,transform 0.15s;
}
.pdf-btn:hover{background:#00B884;box-shadow:0 4px 14px rgba(0,229,160,0.30);transform:translateY(-1px)}
.pdf-btn:active{transform:translateY(0)}

/* ── Section label ── */
.sec{
  font-size:11px;font-weight:700;letter-spacing:1.3px;
  text-transform:uppercase;color:#0D1B17;
  padding-left:10px;border-left:3px solid #00B884;
  margin:0 0 1rem;
}

/* ── Cards ── */
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:0.8rem;margin-bottom:2rem}
.cards-3{display:grid;grid-template-columns:repeat(3,1fr);gap:0.8rem;margin-bottom:2rem}
.cards-5{display:grid;grid-template-columns:repeat(5,1fr);gap:0.8rem;margin-bottom:2rem}
.card{
  background:#FFFFFF;
  border:1px solid #E8EFEC;
  border-top:3px solid #00B884;
  border-radius:10px;padding:1.1rem 1.2rem;
  box-shadow:0 1px 4px rgba(0,229,160,0.08);
}
.card-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.cico{font-size:20px}
.cpct{
  text-align:right;font-size:17px;font-weight:700;color:#00805C;line-height:1.1;
}
.cpct-label{font-size:10px;font-weight:400;color:#0D1B17;text-transform:uppercase;letter-spacing:.5px}
.clabel{font-size:10px;text-transform:uppercase;letter-spacing:.8px;color:#0D1B17;margin-bottom:5px}
.cv{font-size:26px;font-weight:700;color:#00805C;margin-bottom:3px}
.cdetail{font-size:11px;color:#0D1B17}

/* ── Table wrapper ── */
.tw{border-radius:10px;border:1px solid #E8EFEC;overflow:hidden;box-shadow:0 1px 4px rgba(0,229,160,0.07)}
table{width:100%;border-collapse:collapse;font-size:12.5px}

/* ── Table head ── */
thead{background:#00805C}
th{
  padding:11px 13px;text-align:center;
  color:#FFFFFF;font-weight:600;
  font-size:11px;text-transform:uppercase;letter-spacing:.7px;
  border-bottom:2px solid #00B884;
  white-space:nowrap;
}

/* ── Table body ── */
td{
  padding:9px 13px;text-align:center;
  color:#0D1B17;
  border-bottom:1px solid #F2F7F5;
}
td.tdl{text-align:left}
tbody tr:nth-child(even){background:#F2F7F5}
tbody tr:nth-child(odd){background:#FFFFFF}
tbody tr:hover{background:#E8EFEC}
tbody td.hi,tbody td strong.hi{color:#00805C;font-weight:700}

/* ── Footer ── */
.footer{
  margin-top:2rem;padding-top:1rem;
  border-top:1px solid #E8EFEC;
  font-size:11px;color:#0D1B17;
  display:flex;justify-content:space-between;align-items:center;
}

/* ── Print ── */
@media print{
  .pdf-btn{display:none!important}

  html,body,div,span,
  .card,.cards,.cards-3,.cards-5,.tw,.header,.hright,.sec,.footer,
  table,thead,tbody,tr,th,td{
    -webkit-print-color-adjust:exact!important;
    print-color-adjust:exact!important;
    color-adjust:exact!important;
  }

  body{
    padding:1.2rem 1.8rem;
    background:#FFFFFF!important;
    color:#0D1B17!important;
  }

  .card{
    break-inside:avoid;
    background:#FFFFFF!important;
    border-top-color:#0D1B17!important;
    box-shadow:none!important;
    border-color:#0D1B17!important;
  }
  .cv{color:#00805C!important}
  .cpct{color:#00805C!important}
  .clabel,.cdetail,.hsub{color:#0D1B17!important}
  .htitle{color:#00805C!important}
  .htitle span{color:#0D1B17!important}

  thead,thead tr{background:#00805C!important}
  th{
    background:#00805C!important;
    color:#FFFFFF!important;
    border-bottom:2px solid #00B884!important;
    -webkit-print-color-adjust:exact!important;
    print-color-adjust:exact!important;
  }

  tbody tr:nth-child(odd){
    background:#FFFFFF!important;
    -webkit-print-color-adjust:exact!important;
    print-color-adjust:exact!important;
  }
  tbody tr:nth-child(even){
    background:#F2F7F5!important;
    -webkit-print-color-adjust:exact!important;
    print-color-adjust:exact!important;
  }
  tbody td{
    color:#0D1B17!important;
    border-bottom:1px solid #F2F7F5!important;
  }
  tbody td strong.hi{color:#00805C!important}

  th,td{padding:7px 10px}
  .footer{
    margin-top:1rem;
    color:#0D1B17!important;
    border-top-color:#0D1B17!important;
  }
}
"""


# ── HTML generator for general Defect Report ──────────────────────────────────

def _generate_html(fdf: pd.DataFrame, tdf: pd.DataFrame) -> str:
    cards      = _build_cards(fdf, tdf)
    thr        = _get_thresholds(tdf)
    rows       = _build_rows(fdf, thr)
    n          = len(fdf)
    ts         = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M")

    cards_html = ""
    for c in cards:
        cards_html += f"""
        <div class="card">
          <div class="card-top">
            <span class="cico">{c['icon']}</span>
            <span class="cpct">{c['pct']}<br><span class="cpct-label">do total</span></span>
          </div>
          <div class="clabel">{c['label']}</div>
          <div class="cv">{c['value']}</div>
          <div class="cdetail">{c['detail']}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório de Defeitos · Produção</title>
<style>
{_SHARED_CSS}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="htitle">🔍 Relatório de Defeitos · <span>Controle de Qualidade</span></div>
    <div class="hsub">Linha de Acabamento &nbsp;·&nbsp; <strong>{n:,}</strong> registros filtrados &nbsp;·&nbsp; Gerado em {ts}</div>
  </div>
  <div class="hright">
    <span class="hbadge">📊 Visualização Filtrada</span>
    <button class="pdf-btn" onclick="window.print()">🖨️ Baixar PDF</button>
  </div>
</div>

<!-- KPI Cards -->
<div class="sec">Resumo Executivo</div>
<div class="cards">{cards_html}</div>

<!-- Table -->
<div class="sec">Dados Detalhados &nbsp;({n:,} registros)</div>
<div class="tw">
<table>
  <thead>
    <tr>
      <th style="text-align:left">Fornecedor</th>
      <th>OM</th><th>Data Produção</th><th>Qtd</th>
      <th style="text-align:left">Remonte / Defeito</th>
      <th>Real Cortado</th><th>Min. Gerados</th><th>Valor (R$)</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>Dashboard de Qualidade · Produção Acabamento</span>
  <span>{n:,} registros &nbsp;·&nbsp; {ts}</span>
</div>

</body>
</html>"""


# ── HTML generator for Defect History (table only, no KPI cards) ──────────────

def _generate_defeitos_tabela_html(
    fdf: pd.DataFrame,
    filters_desc: str,
    titulo: str = "🗂️ Histórico de Defeitos",
    badge: str = "Registro Permanente",
) -> str:
    """Relatório do histórico de defeitos — apenas a tabela de dados, sem cards."""
    thr  = _get_thresholds(fdf)
    rows = _build_rows(fdf, thr)
    n    = len(fdf)
    ts   = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo} · Qualidade</title>
<style>
{_SHARED_CSS}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="htitle">{titulo} · <span>Controle de Qualidade</span></div>
    <div class="hsub">{filters_desc} &nbsp;·&nbsp; <strong>{n:,}</strong> registros &nbsp;·&nbsp; Gerado em {ts}</div>
  </div>
  <div class="hright">
    <span class="hbadge">{badge}</span>
    <button class="pdf-btn" onclick="window.print()">🖨️ Baixar PDF</button>
  </div>
</div>

<!-- Table -->
<div class="sec">Dados Detalhados &nbsp;({n:,} registros)</div>
<div class="tw">
<table>
  <thead>
    <tr>
      <th style="text-align:left">Fornecedor</th>
      <th>OM</th><th>Data Produção</th><th>Qtd</th>
      <th style="text-align:left">Remonte / Defeito</th>
      <th>Real Cortado</th><th>Min. Gerados</th><th>Valor (R$)</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>{titulo} · Controle de Qualidade</span>
  <span>{n:,} registros &nbsp;·&nbsp; {ts}</span>
</div>

</body>
</html>"""


def _dias_para_vencer_info(dias_para_vencer: int) -> tuple[str, str]:
    """
    Retorna (texto, cor) para o indicador de Dias para Vencer no documento
    impresso/PDF:
      - negativo -> vencido (vermelho)
      - zero     -> vence hoje (âmbar)
      - positivo -> dias restantes (verde)
    """
    if dias_para_vencer < 0:
        return f"Vencido há {abs(dias_para_vencer)} dia(s)", "#D85A30"
    if dias_para_vencer == 0:
        return "Vence hoje", "#EF9F27"
    return f"{dias_para_vencer} dia(s)", "#00805C"


# ── HTML generator for Supplier Billing Report ─────────────────────────────────

def _generate_cobranca_html(
    supplier: str,
    cnpj: str,
    total: float,
    df_sel: pd.DataFrame,
    df_full: pd.DataFrame,
    data_cobranca: date,
    data_vencimento: date,
    dias_para_vencer: int,
) -> str:
    n_records = len(df_sel)
    n_orders = df_sel[COLS["order"]].nunique() if COLS["order"] in df_sel.columns else 0
    ts = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M")

    thr = _get_thresholds(df_full)

    data_cobranca_str  = data_cobranca.strftime("%d/%m/%Y")
    data_vencimento_str = data_vencimento.strftime("%d/%m/%Y")
    dias_texto, dias_cor = _dias_para_vencer_info(dias_para_vencer)
    
    rows = ""
    for _, row in df_sel.iterrows():
        qty = int(row[COLS["quantity"]])
        vbrl = float(row[COLS["value_brl"]])
        mins = float(row[COLS["minutes"]])
        
        dt_val = row[COLS["date"]]
        if isinstance(dt_val, pd.Timestamp):
            dt_str = dt_val.strftime("%d/%m/%Y")
        else:
            dt_str = str(dt_val)
            
        rows += (
            "<tr>"
            f"<td class='tdl'>{supplier}</td>"
            f"<td>{_fmt_int(row[COLS['order']])}</td>"
            f"<td>{dt_str}</td>"
            f"<td>{_b(f'{qty:,}', qty, thr['qty'])}</td>"
            f"<td class='tdl'>{row[COLS['defect']]}</td>"
            f"<td>{_fmt_int(row[COLS['real_cut']])}</td>"
            f"<td>{_b(f'{mins:,.2f}', mins, thr['mins'])}</td>"
            f"<td>{_b(f'R$ {vbrl:,.2f}', vbrl, thr['vbrl'])}</td>"
            "</tr>"
        )
        
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aviso de Cobrança · {supplier}</title>
<style>
{_SHARED_CSS}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="htitle">💰 Aviso de Cobrança · <span>{supplier}</span></div>
    <div class="hsub">CNPJ: {cnpj} &nbsp;·&nbsp; Gerado em {ts}</div>
  </div>
  <div class="hright">
    <span class="hbadge">Gestão de Desconto</span>
    <button class="pdf-btn" onclick="window.print()">🖨️ Baixar PDF</button>
  </div>
</div>

<!-- KPI Cards -->
<div class="sec">Resumo da Cobrança</div>
<div class="cards-3">
  <div class="card">
    <div class="card-top">
      <span class="cico">💰</span>
    </div>
    <div class="clabel">Total a Cobrar</div>
    <div class="cv">R$ {total:,.2f}</div>
    <div class="cdetail">Desconto acumulado</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">📋</span>
    </div>
    <div class="clabel">Registros de Defeito</div>
    <div class="cv">{n_records:,}</div>
    <div class="cdetail">defeitos identificados</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">📦</span>
    </div>
    <div class="clabel">Ordens Mestre (OM)</div>
    <div class="cv">{n_orders:,}</div>
    <div class="cdetail">ordens afetadas</div>
  </div>
</div>

<!-- Prazo de Pagamento -->
<div class="sec">Prazo de Pagamento</div>
<div class="cards-3">
  <div class="card">
    <div class="card-top">
      <span class="cico">🗓️</span>
    </div>
    <div class="clabel">Data da Cobrança</div>
    <div class="cv">{data_cobranca_str}</div>
    <div class="cdetail">data de emissão do aviso</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">📌</span>
    </div>
    <div class="clabel">Data de Vencimento</div>
    <div class="cv">{data_vencimento_str}</div>
    <div class="cdetail">cobrança + 20 dias</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">⏳</span>
    </div>
    <div class="clabel">Dias para Vencer</div>
    <div class="cv"><span style="color:{dias_cor}">{dias_texto}</span></div>
    <div class="cdetail">a partir de hoje</div>
  </div>
</div>

<!-- Table -->
<div class="sec">Detalhamento dos Defeitos</div>
<div class="tw">
<table>
  <thead>
    <tr>
      <th style="text-align:left">Fornecedor</th><th>OM</th><th>Data Produção</th><th>Qtd</th>
      <th style="text-align:left">Remonte / Defeito</th>
      <th>Real Cortado</th><th>Min. Gerados</th><th>Valor (R$)</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>Aviso de Cobrança · Controle de Qualidade</span>
  <span>{n_records:,} registros &nbsp;·&nbsp; {ts}</span>
</div>

</body>
</html>"""


# ── HTML generator for Supplier Range Filter (grouped by supplier) ────────────

def _generate_fornecedores_faixa_html(
    summary: pd.DataFrame,
    metric_label: str,
    low: float,
    high: float,
    is_valor: bool,
) -> str:
    """Relatório dos fornecedores dentro da faixa selecionada, agrupados.

    `summary` segue o contrato de `DataProcessor.supplier_summary`
    (colunas fornecedor / total_remonte / total_ordens / total_valor).
    Colunas do relatório: Fornecedor · Total de Remontes · Total de Ordens ·
    Total em Valor (R$).
    """
    ts = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M")
    n = len(summary)

    if is_valor:
        faixa_desc = f"{metric_label}: R$ {low:,.2f} – R$ {high:,.2f}"
    else:
        faixa_desc = f"{metric_label}: {int(low):,} – {int(high):,}"

    tot_remonte = int(summary["total_remonte"].sum()) if n else 0
    tot_qtd     = int(summary["total_quantidade"].sum()) if n else 0
    tot_ordens  = int(summary["total_ordens"].sum()) if n else 0
    tot_valor   = float(summary["total_valor"].sum()) if n else 0.0

    rows = ""
    for _, row in summary.iterrows():
        rows += (
            "<tr>"
            f"<td class='tdl'>{row['fornecedor']}</td>"
            f"<td>{int(row['total_remonte']):,}</td>"
            f"<td>{int(row['total_quantidade']):,}</td>"
            f"<td>{int(row['total_ordens']):,}</td>"
            f"<td>R$ {float(row['total_valor']):,.2f}</td>"
            "</tr>"
        )
    if not rows:
        rows = "<tr><td class='tdl' colspan='5'>Nenhum fornecedor nesta faixa.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fornecedores por Faixa · Qualidade</title>
<style>
{_SHARED_CSS}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="htitle">🎯 Fornecedores por Faixa · <span>Controle de Qualidade</span></div>
    <div class="hsub">{faixa_desc} &nbsp;·&nbsp; <strong>{n:,}</strong> fornecedor(es) &nbsp;·&nbsp; Gerado em {ts}</div>
  </div>
  <div class="hright">
    <span class="hbadge">Filtro por Faixa</span>
    <button class="pdf-btn" onclick="window.print()">🖨️ Baixar PDF</button>
  </div>
</div>

<!-- KPI Cards -->
<div class="sec">Resumo da Faixa</div>
<div class="cards-3">
  <div class="card">
    <div class="card-top"><span class="cico">🏭</span></div>
    <div class="clabel">Fornecedores</div>
    <div class="cv">{n:,}</div>
    <div class="cdetail">dentro da faixa</div>
  </div>
  <div class="card">
    <div class="card-top"><span class="cico">🔁</span></div>
    <div class="clabel">Total de Remontes</div>
    <div class="cv">{tot_remonte:,}</div>
    <div class="cdetail">{tot_qtd:,} peças na faixa</div>
  </div>
  <div class="card">
    <div class="card-top"><span class="cico">💰</span></div>
    <div class="clabel">Total em Valor</div>
    <div class="cv">R$ {tot_valor:,.2f}</div>
    <div class="cdetail">{tot_ordens:,} ordens (OM)</div>
  </div>
</div>

<!-- Table -->
<div class="sec">Fornecedores &nbsp;({n:,})</div>
<div class="tw">
<table>
  <thead>
    <tr>
      <th style="text-align:left">Fornecedor</th>
      <th>Total de Remontes</th>
      <th>Quantidade</th>
      <th>Total de Ordens</th>
      <th>Total em Valor (R$)</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>Fornecedores por Faixa · Controle de Qualidade</span>
  <span>{n:,} fornecedor(es) &nbsp;·&nbsp; {ts}</span>
</div>

</body>
</html>"""


# ── HTML generator for Billing History Report ─────────────────────────────────

def _generate_historico_html(
    df_filtered: pd.DataFrame,
    totals: dict,
    filters_desc: str,
    titulo: str = "🗃️ Histórico de Cobranças",
    badge: str = "bd_cobranca.xlsx",
) -> str:
    ts = datetime.now(_TZ_BR).strftime("%d/%m/%Y %H:%M")
    n = len(df_filtered)
    
    rows = ""
    for _, row in df_filtered.iterrows():
        supplier = row.get("Fornecedor", "")
        om = row.get("OM", "")
        val_prod = row.get("Data Produção", "")
        qty = row.get("Qtd", 0)
        remonte = row.get("Remonte", "")
        real_cortado = row.get("Real Cortado", 0)
        minutes = row.get("Min. Gerados", 0.0)
        value = row.get("Valor (R$)", 0.0)

        if isinstance(val_prod, pd.Timestamp):
            val_prod = val_prod.strftime("%d/%m/%Y")

        qty_val = _fmt_int(qty)
        om_val  = _fmt_int(om, sep=False)   # OM é identificador, sem milhar
        rc_val  = _fmt_int(real_cortado)

        rows += (
            "<tr>"
            f"<td class='tdl'>{supplier}</td>"
            f"<td>{om_val}</td>"
            f"<td>{val_prod}</td>"
            f"<td>{qty_val}</td>"
            f"<td class='tdl'>{remonte}</td>"
            f"<td>{rc_val}</td>"
            f"<td>{float(minutes):,.2f}</td>"
            f"<td>R$ {float(value):,.2f}</td>"
            "</tr>"
        )
        
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo} · Qualidade</title>
<style>
{_SHARED_CSS}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="htitle">{titulo} · <span>Controle de Qualidade</span></div>
    <div class="hsub">{filters_desc} &nbsp;·&nbsp; Gerado em {ts}</div>
  </div>
  <div class="hright">
    <span class="hbadge">{badge}</span>
    <button class="pdf-btn" onclick="window.print()">🖨️ Baixar PDF</button>
  </div>
</div>

<!-- KPI Cards -->
<div class="sec">Resumo do Histórico</div>
<div class="cards-5">
  <div class="card">
    <div class="card-top">
      <span class="cico">🧵</span>
    </div>
    <div class="clabel">Peças com Defeito</div>
    <div class="cv">{totals['total_pieces']:,}</div>
    <div class="cdetail">total no período</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">📋</span>
    </div>
    <div class="clabel">Total Defeitos</div>
    <div class="cv">{totals['n_records']:,}</div>
    <div class="cdetail">registros/linhas</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">⏱️</span>
    </div>
    <div class="clabel">Total Minutos</div>
    <div class="cv">{totals['total_minutes']:,.0f} min</div>
    <div class="cdetail">tempo gerado</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">💰</span>
    </div>
    <div class="clabel">Valor Total</div>
    <div class="cv">R$ {totals['total_value']:,.2f}</div>
    <div class="cdetail">custo de remonte</div>
  </div>
  <div class="card">
    <div class="card-top">
      <span class="cico">📦</span>
    </div>
    <div class="clabel">Ordens Únicas (OM)</div>
    <div class="cv">{totals['n_orders']:,}</div>
    <div class="cdetail">ordens afetadas</div>
  </div>
</div>

<!-- Table -->
<div class="sec">Registros Detalhados &nbsp;({n:,} linhas)</div>
<div class="tw">
<table>
  <thead>
    <tr>
      <th style="text-align:left">Fornecedor</th><th>OM</th><th>Data Produção</th><th>Qtd</th>
      <th style="text-align:left">Remonte / Defeito</th><th>Real Cortado</th>
      <th>Min. Gerados</th><th>Valor (R$)</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>{titulo} · Controle de Qualidade</span>
  <span>{n:,} registros &nbsp;·&nbsp; {ts}</span>
</div>

</body>
</html>"""

