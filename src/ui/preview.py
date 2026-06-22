"""
Preview page generator — tema clean light.
Fundo branco, acentos #00B884 / #00805C, warmth #F2F7F5.
"""

from datetime import date, datetime
import pandas as pd
from src.config.settings import COLS
from src.data.cobranca_history import payment_punctuality


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


def _build_rows(fdf: pd.DataFrame, thr: dict) -> str:
    d = fdf.copy()
    d[COLS["date"]]        = d[COLS["date"]].dt.strftime("%d/%m/%Y")
    d[COLS["pct_remonte"]] = (d[COLS["pct_remonte"]] * 100).round(2)
    d[COLS["value_brl"]]   = d[COLS["value_brl"]].round(2)
    d[COLS["minutes"]]     = d[COLS["minutes"]].round(2)

    def _make_row(row):
        qty  = int(row[COLS["quantity"]])
        vbrl = float(row[COLS["value_brl"]])
        mins = float(row[COLS["minutes"]])
        pct  = float(row[COLS["pct_remonte"]])
        return (
            "<tr>"
            f"<td>{row[COLS['date']]}</td>"
            f"<td>{int(row[COLS['order']]):,}</td>"
            f"<td class='tdl'>{row[COLS['supplier']]}</td>"
            f"<td>{row[COLS['location']]}</td>"
            f"<td>{row[COLS['defect']]}</td>"
            f"<td>{_b(f'{qty:,}', qty, thr['qty'])}</td>"
            f"<td>{int(row[COLS['real_cut']]):,}</td>"
            f"<td>{pct:.2f}%</td>"
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

/* ── Status badges ── */
.badge-status {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  display: inline-block;
}
.status-pago { background: #00B884; color: #FFFFFF; }
.status-pendente { background: #EF9F27; color:#FFFFFF; }
.status-contestado { background: #D85A30; color: #FFFFFF; }

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
  table,thead,tbody,tr,th,td,.badge-status,.status-pago,.status-pendente,.status-contestado{
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

  .badge-status{
    -webkit-print-color-adjust:exact!important;
    print-color-adjust:exact!important;
    color-adjust:exact!important;
  }
  .status-pago{ background-color:#0D1B17 !important; color: #FFFFFF !important; }
  .status-pendente{ background-color: #EF9F27 !important; color:#FFFFFF !important; }
  .status-contestado{ background-color: #D85A30 !important; color: #FFFFFF !important; }

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
    ts         = datetime.now().strftime("%d/%m/%Y %H:%M")

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
      <th>Data</th><th>Ordem</th>
      <th style="text-align:left">Fornecedor</th>
      <th>Local</th><th>Defeito</th><th>Qtd</th>
      <th>Real Cortado</th><th>% Remonte</th>
      <th>Minutos</th><th>Valor (R$)</th>
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
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")

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
            f"<td>{dt_str}</td>"
            f"<td>{int(row[COLS['order']]):,}</td>"
            f"<td>{_b(f'{qty:,}', qty, thr['qty'])}</td>"
            f"<td class='tdl'>{row[COLS['defect']]}</td>"
            f"<td>{int(row[COLS['real_cut']]):,}</td>"
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
      <th>Data</th><th>OM</th><th>Qtd</th>
      <th style="text-align:left">Remonte / Tipo de Defeito</th>
      <th>Rel. Cortado</th><th>Min. Gerados</th><th>Valor (R$)</th>
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


# ── HTML generator for Billing History Report ─────────────────────────────────

def _generate_historico_html(df_filtered: pd.DataFrame, totals: dict, filters_desc: str) -> str:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    n = len(df_filtered)
    
    rows = ""
    for _, row in df_filtered.iterrows():
        val_cobranca = row.get("Data Cobrança", "")
        val_vencimento = row.get("Data Vencimento", "")
        val_pagamento = row.get("Data Pagamento", "")
        supplier = row.get("Fornecedor", "")
        cnpj = row.get("CNPJ", "")
        status = row.get("Status", "Pendente")
        om = row.get("OM", "")
        val_prod = row.get("Data Produção", "")
        qty = row.get("Qtd", 0)
        remonte = row.get("Remonte", "")
        real_cortado = row.get("Real Cortado", 0)
        minutes = row.get("Min. Gerados", 0.0)
        value = row.get("Valor (R$)", 0.0)
        
        if isinstance(val_cobranca, pd.Timestamp):
            val_cobranca = val_cobranca.strftime("%d/%m/%Y")
        if isinstance(val_vencimento, pd.Timestamp):
            val_vencimento = val_vencimento.strftime("%d/%m/%Y")
        if isinstance(val_pagamento, pd.Timestamp):
            val_pagamento = val_pagamento.strftime("%d/%m/%Y")
        if isinstance(val_prod, pd.Timestamp):
            val_prod = val_prod.strftime("%d/%m/%Y")
        if pd.isna(val_pagamento):
            val_pagamento = ""

        st_lower = str(status).strip()

        # Dias para Vencer / Situação de Pagamento:
        #   - Pendente/Contestado -> contagem regressiva (calculada em tempo
        #     real, não é salva no xlsx pois muda todos os dias).
        #   - Pago -> compara a Data de Pagamento (manual) com a Data de
        #     Vencimento e mostra se foi pago no prazo ou com atraso.
        dias_html = ""
        if st_lower == "Pago":
            dias_atraso, atrasado = payment_punctuality(val_pagamento, val_vencimento)
            if atrasado is None:
                dias_html = '<span style="color:#D8932E;font-weight:600">Informe a data do pagamento</span>'
            elif atrasado:
                dias_html = f'<span style="color:#D85A30;font-weight:600">⚠️ Pago com {dias_atraso}d de atraso</span>'
            else:
                dias_html = '<span style="color:#1D9E75;font-weight:600">✅ Pago no prazo</span>'
        else:
            venc_dt = pd.to_datetime(val_vencimento, format="%d/%m/%Y", errors="coerce")
            if pd.notna(venc_dt):
                dias_val = (venc_dt.date() - date.today()).days
                _dias_texto, _dias_cor = _dias_para_vencer_info(dias_val)
                dias_html = f'<span style="color:{_dias_cor};font-weight:600">{_dias_texto}</span>'

        if st_lower == "Pago":
            status_badge = '<span class="badge-status status-pago">✅ Pago</span>'
        elif st_lower == "Contestado":
            status_badge = '<span class="badge-status status-contestado">⚠️ Contestado</span>'
        else:
            status_badge = '<span class="badge-status status-pendente">⏳ Pendente</span>'
            
        # Formatar números de forma amigável
        try:
            qty_val = f"{int(qty):,}"
        except Exception:
            qty_val = str(qty)
        try:
            om_val = f"{int(om)}"
        except Exception:
            om_val = str(om)
        try:
            rc_val = f"{int(real_cortado):,}"
        except Exception:
            rc_val = str(real_cortado)
            
        rows += (
            "<tr>"
            f"<td>{val_cobranca}</td>"
            f"<td>{val_vencimento}</td>"
            f"<td>{val_pagamento}</td>"
            f"<td>{dias_html}</td>"
            f"<td class='tdl'>{supplier}</td>"
            f"<td>{cnpj}</td>"
            f"<td>{status_badge}</td>"
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
<title>Histórico de Cobranças · Qualidade</title>
<style>
{_SHARED_CSS}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div>
    <div class="htitle">🗃️ Histórico de Cobranças · <span>Controle de Qualidade</span></div>
    <div class="hsub">{filters_desc} &nbsp;·&nbsp; Gerado em {ts}</div>
  </div>
  <div class="hright">
    <span class="hbadge">bd_cobranca.xlsx</span>
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
      <th>Data Cobrança</th><th>Vencimento</th><th>Pagamento</th><th>Situação</th>
      <th style="text-align:left">Fornecedor</th><th>CNPJ</th>
      <th>Status</th><th>OM</th><th>Data Produção</th><th>Qtd</th>
      <th style="text-align:left">Remonte / Defeito</th><th>Real Cortado</th>
      <th>Min. Gerados</th><th>Valor (R$)</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
</div>

<!-- Footer -->
<div class="footer">
  <span>Histórico de Cobranças · Controle de Qualidade</span>
  <span>{n:,} registros &nbsp;·&nbsp; {ts}</span>
</div>

</body>
</html>"""

