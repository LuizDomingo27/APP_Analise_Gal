# -*- coding: utf-8 -*-
"""
Testes do gerador de HTML de impressão/pré-visualização (src/ui/preview.py).

Garante que os 3 relatórios impressos (Análise de Defeitos, Aviso de
Cobrança e Histórico de Cobranças) sempre exibem exatamente as 8 colunas
padronizadas — Fornecedor, OM, Data Produção, Qtd, Remonte/Defeito,
Real Cortado, Min. Gerados e Valor — evitando que colunas extras
estourem a largura da página ao imprimir/exportar em PDF. Também garante
que o horário exibido usa sempre o fuso do Brasil, independente do
fuso do servidor.
"""

import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import src.ui.preview as preview
from src.config.settings import COLS

_EXPECTED_HEADERS = [
    "Fornecedor", "OM", "Data Produção", "Qtd",
    "Remonte / Defeito", "Real Cortado", "Min. Gerados", "Valor (R$)",
]


def _extract_headers(html: str) -> list[str]:
    thead = html.split("<thead>")[1].split("</thead>")[0]
    return re.findall(r"<th[^>]*>(.*?)</th>", thead)


def _make_defect_df() -> pd.DataFrame:
    return pd.DataFrame({
        COLS["date"]:        pd.to_datetime(["2026-07-01", "2026-07-02"]),
        COLS["order"]:       [1001, 1002],
        COLS["supplier"]:    ["Fornecedor A", "Fornecedor B"],
        COLS["location"]:    ["Local X", "Local Y"],
        COLS["defect"]:      ["PONTO ESTOURADO", "SEM ARREMATE"],
        COLS["quantity"]:    [10, 20],
        COLS["real_cut"]:    [5, 8],
        COLS["pct_remonte"]: [0.1, 0.2],
        COLS["minutes"]:     [15.5, 30.0],
        COLS["value_brl"]:   [100.0, 200.0],
    })


def test_generate_html_has_exactly_the_8_standard_columns():
    df = _make_defect_df()
    html = preview._generate_html(df, df)
    assert _extract_headers(html) == _EXPECTED_HEADERS


def test_generate_cobranca_html_includes_fornecedor_and_8_columns():
    df = _make_defect_df()
    html = preview._generate_cobranca_html(
        supplier="Fornecedor A",
        cnpj="12.345.678/0001-90",
        total=300.0,
        df_sel=df,
        df_full=df,
        data_cobranca=date.today(),
        data_vencimento=date.today() + timedelta(days=20),
        dias_para_vencer=20,
    )
    assert _extract_headers(html) == _EXPECTED_HEADERS
    assert "Fornecedor A" in html.split("<tbody>")[1]


def test_generate_historico_html_reduces_15_columns_to_8():
    totals = dict(n_records=1, total_minutes=15.5, total_value=100.0,
                  total_pieces=10, n_orders=1, n_cobrancas=1)
    df_hist = pd.DataFrame({
        "Código":          ["COD-1"],
        "Data Cobrança":   ["01/06/2026"],
        "Data Vencimento": ["21/06/2026"],
        "Data Pagamento":  [""],
        "Fornecedor":      ["Fornecedor A"],
        "CNPJ":            ["12.345.678/0001-90"],
        "Status":          ["Pendente"],
        "OM":              [1001],
        "Data Produção":   [pd.Timestamp("2026-07-01")],
        "Qtd":             [10],
        "Remonte":         ["PONTO ESTOURADO"],
        "Real Cortado":    [5],
        "Min. Gerados":    [15.5],
        "Valor (R$)":      [100.0],
    })
    html = preview._generate_historico_html(df_hist, totals, "Período: todos")

    headers = _extract_headers(html)
    assert headers == _EXPECTED_HEADERS

    row_html = html.split("<tbody>")[1].split("</tbody>")[0]
    # Colunas mantidas.
    assert "Fornecedor A" in row_html
    assert "PONTO ESTOURADO" in row_html
    # Colunas de rastreamento removidas apenas da tabela impressa — a
    # lógica de status/situação em si (cobranca_history.py) não é tocada.
    assert "COD-1" not in row_html
    assert "12.345.678/0001-90" not in row_html


def test_print_timestamp_uses_brazil_timezone_not_server_local():
    assert preview._TZ_BR == ZoneInfo("America/Sao_Paulo")

    df = _make_defect_df()
    html = preview._generate_html(df, df)
    match = re.search(r"Gerado em (\d{2}/\d{2}/\d{4} \d{2}:\d{2})", html)
    assert match is not None
