# -*- coding: utf-8 -*-
"""
Testes do novo filtro de fornecedores por faixa (substitui as tabelas de
frequência). Cobre:

  · DataProcessor.supplier_summary        — agregação por fornecedor;
  · DataProcessor.supplier_summary_in_range — filtro por faixa [low, high];
  · preview._generate_fornecedores_faixa_html — relatório/PDF agrupado.

Camada pura sobre DataFrame em memória — sem banco de dados.
"""

import pandas as pd
import pytest

from src.config.settings import COLS
from src.data.processor import DataProcessor
from src.ui.preview import _generate_fornecedores_faixa_html


def _df(rows: list[tuple]) -> pd.DataFrame:
    """Cada linha: (fornecedor, ordem, quantidade, valor_brl)."""
    return pd.DataFrame(
        {
            COLS["supplier"]:  [r[0] for r in rows],
            COLS["order"]:     [r[1] for r in rows],
            COLS["quantity"]:  [r[2] for r in rows],
            COLS["value_brl"]: [r[3] for r in rows],
        }
    )


# ── supplier_summary ──────────────────────────────────────────────────────────

def test_supplier_summary_agrega_remonte_ordens_e_valor():
    # A: 3 remontes (linhas), ordens {1,1,2}=2 únicas, valor 600
    # B: 1 remonte, 1 ordem, valor 1000
    df = _df([
        ("A", 1, 5, 100.0),
        ("A", 1, 5, 200.0),
        ("A", 2, 5, 300.0),
        ("B", 9, 5, 1000.0),
    ])
    res = DataProcessor(df).supplier_summary()

    assert list(res.columns) == [
        "fornecedor", "total_remonte", "total_quantidade",
        "total_ordens", "total_valor",
    ]
    # Ordenado por valor total desc → B (1000) antes de A (600).
    assert res["fornecedor"].tolist() == ["B", "A"]

    a = res[res["fornecedor"] == "A"].iloc[0]
    assert a["total_remonte"] == 3      # nº de linhas/remontes
    assert a["total_quantidade"] == 15  # 5 + 5 + 5 peças
    assert a["total_ordens"] == 2       # ordens mestre únicas
    assert a["total_valor"] == 600.0

    b = res[res["fornecedor"] == "B"].iloc[0]
    assert b["total_remonte"] == 1
    assert b["total_quantidade"] == 5
    assert b["total_ordens"] == 1
    assert b["total_valor"] == 1000.0


def test_supplier_summary_vazio_retorna_colunas_certas():
    res = DataProcessor(_df([])).supplier_summary()
    assert res.empty
    assert list(res.columns) == [
        "fornecedor", "total_remonte", "total_quantidade",
        "total_ordens", "total_valor",
    ]


# ── supplier_summary_in_range ─────────────────────────────────────────────────

@pytest.fixture
def base_df():
    # Totais por fornecedor:
    #   A: remonte 1, ordens 1, valor 100
    #   B: remonte 2, ordens 2, valor 500
    #   C: remonte 3, ordens 1, valor 3000
    return _df([
        ("A", 1, 1, 100.0),
        ("B", 2, 1, 250.0),
        ("B", 3, 1, 250.0),
        ("C", 4, 1, 1000.0),
        ("C", 4, 1, 1000.0),
        ("C", 4, 1, 1000.0),
    ])


def test_range_por_remonte_inclusivo_nas_pontas(base_df):
    # Remonte entre 2 e 3 → B (2) e C (3); A (1) fora.
    res = DataProcessor(base_df).supplier_summary_in_range("remonte", 2, 3)
    assert set(res["fornecedor"]) == {"B", "C"}


def test_range_por_valor(base_df):
    # Valor entre 200 e 600 → apenas B (500).
    res = DataProcessor(base_df).supplier_summary_in_range("valor", 200.0, 600.0)
    assert res["fornecedor"].tolist() == ["B"]


def test_range_por_ordens(base_df):
    # Ordens exatamente 2 → apenas B.
    res = DataProcessor(base_df).supplier_summary_in_range("ordens", 2, 2)
    assert res["fornecedor"].tolist() == ["B"]


def test_range_inverte_limites_quando_low_maior_que_high(base_df):
    # low > high deve ser tratado como faixa [200, 600] (invertida).
    invertido = DataProcessor(base_df).supplier_summary_in_range("valor", 600.0, 200.0)
    normal    = DataProcessor(base_df).supplier_summary_in_range("valor", 200.0, 600.0)
    assert invertido["fornecedor"].tolist() == normal["fornecedor"].tolist()


def test_range_sem_correspondencia_retorna_vazio(base_df):
    res = DataProcessor(base_df).supplier_summary_in_range("valor", 5000.0, 9000.0)
    assert res.empty
    assert list(res.columns) == [
        "fornecedor", "total_remonte", "total_quantidade",
        "total_ordens", "total_valor",
    ]


def test_range_metrica_invalida_levanta_valueerror(base_df):
    with pytest.raises(ValueError):
        DataProcessor(base_df).supplier_summary_in_range("inexistente", 0, 10)


def test_range_em_df_vazio_nao_levanta():
    res = DataProcessor(_df([])).supplier_summary_in_range("remonte", 0, 10)
    assert res.empty


# ── _generate_fornecedores_faixa_html ─────────────────────────────────────────

def _summary(rows: list[tuple]) -> pd.DataFrame:
    """Cada linha: (fornecedor, total_remonte, total_quantidade, total_ordens, total_valor)."""
    return pd.DataFrame(
        rows,
        columns=[
            "fornecedor", "total_remonte", "total_quantidade",
            "total_ordens", "total_valor",
        ],
    )


def test_html_contem_fornecedores_e_colunas():
    summary = _summary([
        ("Oficina A", 3, 40, 2, 600.0),
        ("Oficina B", 1, 10, 1, 1000.0),
    ])
    html = _generate_fornecedores_faixa_html(
        summary, "Total em Valor (R$)", 200.0, 2000.0, is_valor=True
    )
    assert "Oficina A" in html and "Oficina B" in html
    assert "Total de Remontes" in html
    assert "Quantidade" in html
    assert "Total de Ordens" in html
    assert "R$ 600.00" in html and "R$ 1,000.00" in html
    # Quantidade agregada aparece na tabela.
    assert ">40<" in html and ">10<" in html
    # Faixa em reais no cabeçalho.
    assert "R$ 200.00" in html and "R$ 2,000.00" in html


def test_html_faixa_inteira_para_metrica_nao_monetaria():
    summary = _summary([("Oficina A", 3, 40, 2, 600.0)])
    html = _generate_fornecedores_faixa_html(
        summary, "Total de Remontes", 2, 5, is_valor=False
    )
    assert "Total de Remontes: 2 – 5" in html


def test_html_summary_vazio_nao_levanta():
    summary = _summary([])
    html = _generate_fornecedores_faixa_html(
        summary, "Total de Remontes", 0, 10, is_valor=False
    )
    assert "Nenhum fornecedor nesta faixa." in html
    assert "0 fornecedor(es)" in html
