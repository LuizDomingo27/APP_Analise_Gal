# -*- coding: utf-8 -*-
"""
Testes das melhorias de Análise de Defeitos / Histórico / Cobrança:

  · DataProcessor.current_month / month_label / rows_in_month
  · DataProcessor.by_date_current_month / by_date_cost_current_month
        — gráfico diário restrito ao mês vigente do recorte;
  · DataProcessor.month_over_month
        — card comparativo mês vigente × mês anterior (peças e valor);
  · cobranca_history.situacao_series / situacao_categoria
        — filtro por situação (ex.: somente dívidas vencidas);
  · cobranca_history.count_unique_partners
        — cards de parceiros únicos cobrados / que pagaram.

Camada pura sobre DataFrame em memória — sem banco de dados.
"""

from datetime import date

import pandas as pd
import pytest

from src.config.settings import COLS
from src.data.cobranca_history import (
    SITUACAO_A_VENCER,
    SITUACAO_OPTIONS,
    SITUACAO_PAGA_ATRASO,
    SITUACAO_PAGA_PRAZO,
    SITUACAO_SEM_INFO,
    SITUACAO_VENCE_HOJE,
    SITUACAO_VENCIDA,
    count_unique_partners,
    situacao_categoria,
    situacao_series,
)
from src.data.processor import DataProcessor


def _df(rows: list[tuple]) -> pd.DataFrame:
    """Cada linha: (data ISO, quantidade, valor_brl)."""
    return pd.DataFrame(
        {
            COLS["date"]:      pd.to_datetime([r[0] for r in rows]),
            COLS["quantity"]:  [r[1] for r in rows],
            COLS["value_brl"]: [r[2] for r in rows],
        }
    )


# ══════════════════════════════════════════════════════════════════════════════
# Mês vigente
# ══════════════════════════════════════════════════════════════════════════════

def test_current_month_e_o_mes_da_data_mais_recente():
    df = _df([("2026-06-10", 1, 10.0), ("2026-08-03", 2, 20.0), ("2026-07-30", 3, 30.0)])
    assert DataProcessor(df).current_month() == pd.Period("2026-08", freq="M")


def test_current_month_none_em_base_vazia():
    vazio = _df([]).iloc[0:0]
    assert DataProcessor(vazio).current_month() is None


def test_current_month_ignora_datas_invalidas():
    df = pd.DataFrame(
        {
            COLS["date"]:      pd.to_datetime(["2026-05-02", None]),
            COLS["quantity"]:  [1, 9],
            COLS["value_brl"]: [10.0, 90.0],
        }
    )
    assert DataProcessor(df).current_month() == pd.Period("2026-05", freq="M")


def test_month_label_em_portugues():
    assert DataProcessor.month_label(pd.Period("2026-08", freq="M")) == "Agosto/2026"
    assert DataProcessor.month_label(pd.Period("2026-03", freq="M")) == "Março/2026"
    assert DataProcessor.month_label(None) == "—"


def test_by_date_current_month_descarta_meses_anteriores():
    df = _df([
        ("2026-07-15", 5, 50.0),    # mês anterior — fora
        ("2026-08-01", 3, 30.0),
        ("2026-08-01", 4, 40.0),    # mesma data: agregada
        ("2026-08-20", 7, 70.0),
    ])
    res = DataProcessor(df).by_date_current_month()

    assert len(res) == 2
    assert list(res[COLS["date"]].dt.day) == [1, 20]
    assert res[COLS["quantity"]].tolist() == [7, 7]


def test_by_date_cost_current_month_soma_valores_do_mes():
    df = _df([("2026-07-15", 5, 50.0), ("2026-08-02", 1, 12.5), ("2026-08-02", 1, 7.5)])
    res = DataProcessor(df).by_date_cost_current_month()

    assert len(res) == 1
    assert res[COLS["value_brl"]].iloc[0] == pytest.approx(20.0)


def test_by_date_current_month_vazio_nao_quebra():
    vazio = _df([]).iloc[0:0]
    assert DataProcessor(vazio).by_date_current_month().empty
    assert DataProcessor(vazio).by_date_cost_current_month().empty


# ══════════════════════════════════════════════════════════════════════════════
# Comparativo mensal
# ══════════════════════════════════════════════════════════════════════════════

def test_month_over_month_compara_pecas_e_valor():
    df = _df([
        ("2026-07-05", 100, 1000.0),
        ("2026-07-20",  50,  500.0),   # anterior: 150 peças / R$ 1.500
        ("2026-08-02", 120, 1800.0),   # vigente:  180 peças / R$ 2.100
        ("2026-08-19",  60,  300.0),
    ])
    res = DataProcessor(df).month_over_month()

    assert res["has_current"] and res["has_previous"]
    assert res["current_label"] == "Agosto/2026"
    assert res["previous_label"] == "Julho/2026"
    assert res["current_pieces"] == 180
    assert res["previous_pieces"] == 150
    assert res["pieces_delta"] == 30
    assert res["pieces_pct"] == pytest.approx(20.0)
    assert res["current_value"] == pytest.approx(2100.0)
    assert res["previous_value"] == pytest.approx(1500.0)
    assert res["value_delta"] == pytest.approx(600.0)
    assert res["value_pct"] == pytest.approx(40.0)


def test_month_over_month_queda_gera_variacao_negativa():
    df = _df([("2026-07-05", 200, 2000.0), ("2026-08-05", 150, 1000.0)])
    res = DataProcessor(df).month_over_month()

    assert res["pieces_delta"] == -50
    assert res["pieces_pct"] == pytest.approx(-25.0)
    assert res["value_delta"] == pytest.approx(-1000.0)
    assert res["value_pct"] == pytest.approx(-50.0)


def test_month_over_month_sem_mes_anterior():
    df = _df([("2026-08-05", 10, 100.0)])
    res = DataProcessor(df).month_over_month()

    assert res["has_current"] is True
    assert res["has_previous"] is False
    assert res["previous_pieces"] == 0
    assert res["previous_value"] == pytest.approx(0.0)
    # Sem base de comparação o percentual é None (nunca uma divisão por zero).
    assert res["pieces_pct"] is None
    assert res["value_pct"] is None


def test_month_over_month_pula_mes_sem_dados():
    """Junho tem dados, julho não: o comparativo é sempre com o mês CALENDÁRIO
    anterior — julho, vazio — e não com 'o mês anterior que tinha dados'."""
    df = _df([("2026-06-10", 90, 900.0), ("2026-08-10", 10, 100.0)])
    res = DataProcessor(df).month_over_month()

    assert res["previous_label"] == "Julho/2026"
    assert res["has_previous"] is False
    assert res["previous_pieces"] == 0


def test_month_over_month_em_base_vazia_nao_quebra():
    res = DataProcessor(_df([]).iloc[0:0]).month_over_month()

    assert res["has_current"] is False
    assert res["current_pieces"] == 0
    assert res["current_label"] == "—"


def test_month_over_month_virada_de_ano():
    df = _df([("2025-12-20", 40, 400.0), ("2026-01-05", 60, 600.0)])
    res = DataProcessor(df).month_over_month()

    assert res["current_label"] == "Janeiro/2026"
    assert res["previous_label"] == "Dezembro/2025"
    assert res["pieces_delta"] == 20


# ══════════════════════════════════════════════════════════════════════════════
# Situação dos lançamentos (filtro da aba Histórico de Cobranças)
# ══════════════════════════════════════════════════════════════════════════════

_HOJE = date(2026, 8, 11)


def _situacao(status, venc, pag=""):
    return situacao_categoria(status, venc, pag, hoje=_HOJE)


def test_situacao_vencida_vence_hoje_e_a_vencer():
    assert _situacao("Pendente", "01/08/2026") == SITUACAO_VENCIDA
    assert _situacao("Pendente", "11/08/2026") == SITUACAO_VENCE_HOJE
    assert _situacao("Pendente", "25/08/2026") == SITUACAO_A_VENCER


def test_situacao_de_lancamento_pago():
    assert _situacao("Pago", "10/08/2026", "05/08/2026") == SITUACAO_PAGA_PRAZO
    assert _situacao("Pago", "10/08/2026", "10/08/2026") == SITUACAO_PAGA_PRAZO
    assert _situacao("Pago", "10/08/2026", "15/08/2026") == SITUACAO_PAGA_ATRASO


def test_situacao_sem_informacao():
    # Sem data de vencimento, ou pago sem data de pagamento.
    assert _situacao("Pendente", "") == SITUACAO_SEM_INFO
    assert _situacao("Pendente", None) == SITUACAO_SEM_INFO
    assert _situacao("Pago", "10/08/2026", "") == SITUACAO_SEM_INFO


def test_situacao_todas_as_categorias_estao_no_filtro():
    categorias = {
        _situacao("Pendente", "01/08/2026"),
        _situacao("Pendente", "11/08/2026"),
        _situacao("Pendente", "25/08/2026"),
        _situacao("Pago", "10/08/2026", "05/08/2026"),
        _situacao("Pago", "10/08/2026", "15/08/2026"),
        _situacao("Pendente", ""),
    }
    assert categorias == set(SITUACAO_OPTIONS)


def test_situacao_series_classifica_a_coluna_inteira():
    df = pd.DataFrame(
        {
            "Status":          ["Pendente", "Pendente", "Pago"],
            "Data Vencimento": ["01/08/2026", "25/08/2026", "10/08/2026"],
            "Data Pagamento":  ["", "", "15/08/2026"],
        }
    )
    res = situacao_series(
        df["Status"], df["Data Vencimento"], df["Data Pagamento"], hoje=_HOJE
    )

    assert res.tolist() == [SITUACAO_VENCIDA, SITUACAO_A_VENCER, SITUACAO_PAGA_ATRASO]
    # Filtrar "somente vencidas" devolve apenas a primeira linha.
    assert len(df[res.isin([SITUACAO_VENCIDA])]) == 1


def test_situacao_series_preserva_o_indice_do_recorte():
    df = pd.DataFrame(
        {
            "Status":          ["Pendente", "Pendente"],
            "Data Vencimento": ["01/08/2026", "25/08/2026"],
            "Data Pagamento":  ["", ""],
        },
        index=[7, 42],
    )
    res = situacao_series(
        df["Status"], df["Data Vencimento"], df["Data Pagamento"], hoje=_HOJE
    )
    assert res.index.tolist() == [7, 42]


def test_situacao_series_aceita_timestamp_e_serie_vazia():
    res = situacao_series(
        pd.Series(["Pendente"]),
        pd.Series([pd.Timestamp("2026-08-01")]),
        pd.Series([pd.NaT]),
        hoje=_HOJE,
    )
    assert res.iloc[0] == SITUACAO_VENCIDA

    vazio = situacao_series(pd.Series(dtype=object), pd.Series(dtype=object),
                            pd.Series(dtype=object), hoje=_HOJE)
    assert vazio.empty


# ══════════════════════════════════════════════════════════════════════════════
# Parceiros únicos (cards de Histórico e Pagamentos Concluídos)
# ══════════════════════════════════════════════════════════════════════════════

def test_count_unique_partners_conta_nomes_distintos():
    # O mesmo parceiro aparece em várias cobranças.
    nomes = pd.Series(["Oficina A", "Oficina A", "Oficina B", "Oficina A", "Oficina C"])
    assert count_unique_partners(nomes) == 3


def test_count_unique_partners_normaliza_caixa_e_espacos():
    nomes = pd.Series(["Oficina A", "oficina a", " OFICINA  A ", "Oficina B"])
    assert count_unique_partners(nomes) == 2


def test_count_unique_partners_ignora_vazios_e_nulos():
    nomes = pd.Series(["Oficina A", "", "   ", None, "Oficina B"])
    assert count_unique_partners(nomes) == 2


def test_count_unique_partners_em_serie_vazia():
    assert count_unique_partners(pd.Series(dtype=object)) == 0
    assert count_unique_partners([]) == 0
