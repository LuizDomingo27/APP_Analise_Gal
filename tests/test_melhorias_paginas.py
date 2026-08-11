# -*- coding: utf-8 -*-
"""
Testes de PÁGINA (AppTest) das melhorias:

  · Análise de Defeitos e Histórico de Defeitos
        — card comparativo mês vigente × mês anterior e gráfico diário
          restrito ao mês vigente;
  · Histórico de Cobranças
        — filtro por situação (ex.: somente dívidas vencidas) e card de
          parceiros únicos cobrados;
  · Pagamentos Concluídos
        — card de parceiros únicos que pagaram.

As páginas rodam de verdade sob o AppTest, no mesmo padrão de
tests/test_performance_page.py. Nenhum banco é tocado: as funções de leitura
são substituídas por bases em memória.
"""

import re
from datetime import date, timedelta

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import src.data.cobranca_history as cobranca_history
import src.data.devolucao_history as devolucao_history
import src.data.divida_dividida as divida_dividida
import src.data.historico_defeitos as hist
import src.data.loader as loader
import src.data.payment_history as payment_history
import src.ui.historico_defeitos as hist_ui
from src.config.settings import COLS

USUARIO = {"username": "auditor", "nome": "Auditor", "role": "admin"}

_HOJE = date.today()
_MES_ATUAL = _HOJE.replace(day=1)
_MES_ANTERIOR = (_MES_ATUAL - timedelta(days=1)).replace(day=1)


def _base_defeitos() -> pd.DataFrame:
    """Base com registros no mês vigente e no anterior (para o comparativo)."""
    linhas = [
        (_MES_ANTERIOR,                       "OM100", "OFICINA A", 100, 1000.0),
        (_MES_ANTERIOR + timedelta(days=5),   "OM200", "OFICINA B",  50,  500.0),
        (_MES_ATUAL,                          "OM300", "OFICINA A", 120, 1800.0),
        (_MES_ATUAL + timedelta(days=2),      "OM400", "OFICINA C",  60,  300.0),
    ]
    return pd.DataFrame(
        {
            COLS["date"]:        pd.to_datetime([l[0] for l in linhas]),
            COLS["order"]:       [l[1] for l in linhas],
            COLS["supplier"]:    [l[2] for l in linhas],
            COLS["quantity"]:    [l[3] for l in linhas],
            COLS["value_brl"]:   [l[4] for l in linhas],
            COLS["defect"]:      ["PONTO ESTOURADO"] * len(linhas),
            COLS["location"]:    ["MANGA"] * len(linhas),
            COLS["real_cut"]:    [500] * len(linhas),
            COLS["minutes"]:     [12.5] * len(linhas),
            COLS["pct_remonte"]: [0.02] * len(linhas),
        }
    )


@pytest.fixture
def base_defeitos(monkeypatch):
    """Serve a base em memória no lugar das leituras de disco/banco.

    `src.ui.historico_defeitos` faz `from ... import load_historico` e é
    importado uma única vez por sessão de testes: se outro arquivo de teste já
    o importou, o nome lá dentro aponta para a função ORIGINAL e o patch só no
    módulo de dados não o alcança — a página iria ao banco de verdade. Por isso
    os dois pontos são substituídos.
    """
    monkeypatch.setattr(loader, "load_data_from_disk", lambda: _base_defeitos())
    monkeypatch.setattr(hist, "load_historico", lambda: _base_defeitos())
    monkeypatch.setattr(hist_ui, "load_historico", lambda: _base_defeitos())
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _abrir(pagina: str) -> AppTest:
    at = AppTest.from_file(pagina, default_timeout=180)
    at.session_state["auth_user"] = dict(USUARIO)
    return at.run()


def _todo_o_texto(at: AppTest) -> str:
    partes = [bloco.value for bloco in at.markdown]
    partes += [bloco.value for bloco in at.caption]
    return "\n".join(str(p) for p in partes)


def _valor_do_card(texto: str, rotulo: str) -> str:
    """Valor exibido no card de KPI cujo rótulo é `rotulo`.

    Os cards são HTML gerado por f-string, com quebras de linha e indentação
    entre as tags; comparar o texto cru seria frágil, então o espaço em branco
    é removido antes de procurar o valor logo após o rótulo.
    """
    compacto = re.sub(r"\s+", "", texto)
    alvo = re.sub(r"\s+", "", rotulo)
    assert alvo in compacto, f"card {rotulo!r} não foi renderizado"
    depois = compacto.split(alvo, 1)[1]
    achado = re.search(r">([^<>]+)</div>", depois)
    return achado.group(1) if achado else ""


# ══════════════════════════════════════════════════════════════════════════════
# Análise de Defeitos + Histórico de Defeitos
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "pagina", ["pages/1_Dashboard.py", "pages/2_Historico_Defeitos.py"]
)
def test_pagina_exibe_comparativo_mensal_e_grafico_do_mes_vigente(pagina, base_defeitos):
    at = _abrir(pagina)
    texto = _todo_o_texto(at)

    assert not at.exception
    # Card comparativo: mês vigente × mês anterior, em peças e em valor.
    assert "Comparativo mensal" in texto
    assert "Peças com defeito" in texto
    assert "Custo de remonte" in texto
    # Variação calculada: 180 peças no mês vigente contra 150 no anterior.
    assert "180" in texto and "150" in texto
    # Gráfico por dia declaradamente restrito ao mês vigente.
    assert "mês vigente" in texto
    assert "Defeitos por dia —" in texto


def test_comparativo_sem_mes_anterior_avisa_em_vez_de_inventar_variacao(monkeypatch):
    """Base só com o mês vigente: o card aparece, mas sem percentual fabricado."""
    só_mes_atual = _base_defeitos()
    só_mes_atual = só_mes_atual[
        só_mes_atual[COLS["date"]] >= pd.Timestamp(_MES_ATUAL)
    ].reset_index(drop=True)

    monkeypatch.setattr(loader, "load_data_from_disk", lambda: só_mes_atual.copy())
    st.cache_data.clear()

    at = _abrir("pages/1_Dashboard.py")
    texto = _todo_o_texto(at)

    assert not at.exception
    assert "Comparativo mensal" in texto
    assert "Sem mês anterior no recorte" in texto
    st.cache_data.clear()


def test_pagina_com_base_de_um_unico_dia_nao_quebra(monkeypatch):
    """Recorte mínimo (um dia): gráficos e comparativo continuam de pé."""
    um_dia = _base_defeitos().head(1).reset_index(drop=True)
    monkeypatch.setattr(loader, "load_data_from_disk", lambda: um_dia.copy())
    st.cache_data.clear()

    at = _abrir("pages/1_Dashboard.py")

    assert not at.exception
    st.cache_data.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Histórico de Cobranças / Pagamentos Concluídos
# ══════════════════════════════════════════════════════════════════════════════

def _linha_cobranca(cod, fornecedor, cnpj, venc: date, status="Pendente", pagamento=""):
    return {
        "COD_LANCAMENTO":   cod,
        "DATA_COBRANCA":    (venc - timedelta(days=10)).strftime("%d/%m/%Y"),
        "DATA_VENCIMENTO":  venc.strftime("%d/%m/%Y"),
        "DATA_PAGAMENTO":   pagamento,
        COLS["supplier"]:   fornecedor,
        "CNPJ_FORNECEDOR":  cnpj,
        COLS["status"]:     status,
        COLS["order"]:      "OM900",
        COLS["date"]:       venc.strftime("%d/%m/%Y"),
        COLS["quantity"]:   10,
        COLS["defect"]:     "PONTO ESTOURADO",
        COLS["real_cut"]:   500,
        COLS["minutes"]:    12.5,
        COLS["value_brl"]:  100.0,
    }


def _base_cobrancas() -> pd.DataFrame:
    """Duas cobranças vencidas (mesmo parceiro) e uma a vencer (outro parceiro)."""
    return pd.DataFrame([
        _linha_cobranca("PAG-001", "OFICINA A", "111", _HOJE - timedelta(days=15)),
        _linha_cobranca("PAG-002", "oficina a", "111", _HOJE - timedelta(days=3)),
        _linha_cobranca("PAG-003", "OFICINA B", "222", _HOJE + timedelta(days=20)),
    ])


def _base_pagamentos() -> pd.DataFrame:
    """Três pagamentos de dois parceiros distintos (um deles pagou duas vezes)."""
    return pd.DataFrame([
        _linha_cobranca("PAG-010", "OFICINA A", "111", _HOJE - timedelta(days=30),
                        "Pago", (_HOJE - timedelta(days=32)).strftime("%d/%m/%Y")),
        _linha_cobranca("PAG-011", "OFICINA A", "111", _HOJE - timedelta(days=20),
                        "Pago", (_HOJE - timedelta(days=15)).strftime("%d/%m/%Y")),
        _linha_cobranca("PAG-012", "OFICINA C", "333", _HOJE - timedelta(days=10),
                        "Pago", (_HOJE - timedelta(days=11)).strftime("%d/%m/%Y")),
    ])


@pytest.fixture
def base_cobrancas(monkeypatch):
    """Substitui todas as leituras/migrações de banco da página de cobranças."""
    monkeypatch.setattr(cobranca_history, "load_history", lambda: _base_cobrancas())
    monkeypatch.setattr(cobranca_history, "migrate_paid_to_payments", lambda: 0)
    monkeypatch.setattr(cobranca_history, "migrate_contestado_to_devolucao", lambda: 0)
    monkeypatch.setattr(cobranca_history, "generate_history_xlsx_bytes", lambda: None)
    monkeypatch.setattr(payment_history, "load_payments", lambda: _base_pagamentos())
    monkeypatch.setattr(payment_history, "generate_payments_xlsx_bytes", lambda: None)
    monkeypatch.setattr(devolucao_history, "load_devolucoes", lambda: pd.DataFrame())
    monkeypatch.setattr(
        divida_dividida, "load_dividas_divididas", lambda: pd.DataFrame()
    )
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def test_historico_cobranca_tem_filtro_por_situacao_e_card_de_parceiros(base_cobrancas):
    at = _abrir("pages/3_Historico_Cobranca.py")
    texto = _todo_o_texto(at)

    assert not at.exception
    # "OFICINA A" e "oficina a" são o mesmo parceiro → 2 parceiros, 3 cobranças.
    assert _valor_do_card(texto, "PARCEIROS ÚNICOS COBRADOS") == "2"
    assert _valor_do_card(texto, "COBRANÇAS REALIZADAS") == "3"
    assert at.multiselect(key="hist_situacao_filter") is not None


def test_filtrar_somente_vencidas_reduz_o_recorte(base_cobrancas):
    at = _abrir("pages/3_Historico_Cobranca.py")
    antes = _todo_o_texto(at)
    assert "3 registro(s)" in antes

    at.multiselect(key="hist_situacao_filter").set_value(["Vencida"]).run()
    depois = _todo_o_texto(at)

    assert not at.exception
    assert "Situação: Vencida" in depois
    assert "2 registro(s)" in depois


def test_filtrar_somente_a_vencer_mantem_apenas_a_cobranca_futura(base_cobrancas):
    at = _abrir("pages/3_Historico_Cobranca.py")
    at.multiselect(key="hist_situacao_filter").set_value(["A vencer"]).run()
    texto = _todo_o_texto(at)

    assert not at.exception
    assert "1 registro(s)" in texto
    assert "OFICINA B" in texto


def test_limpar_filtros_restaura_todas_as_situacoes(base_cobrancas):
    at = _abrir("pages/3_Historico_Cobranca.py")
    at.multiselect(key="hist_situacao_filter").set_value(["Vencida"]).run()
    at.button(key="hist_clear").click().run()
    texto = _todo_o_texto(at)

    assert not at.exception
    assert "Situação: todas" in texto
    assert "3 registro(s)" in texto


def test_pagamentos_concluidos_tem_card_de_parceiros_que_pagaram(base_cobrancas):
    at = _abrir("pages/3_Historico_Cobranca.py")
    texto = _todo_o_texto(at)

    assert not at.exception
    # Dois parceiros distintos pagaram (OFICINA A pagou duas cobranças).
    assert _valor_do_card(texto, "PARCEIROS QUE PAGARAM") == "2"
    assert _valor_do_card(texto, "LANÇAMENTOS PAGOS") == "3"


def test_falha_no_calculo_da_situacao_nao_derruba_a_pagina(base_cobrancas, monkeypatch):
    """Fronteira defensiva: sem a situação, o histórico continua sendo exibido."""
    def _falha(*args, **kwargs):
        raise ValueError("formato de data inesperado")

    monkeypatch.setattr(cobranca_history, "situacao_series", _falha)
    at = _abrir("pages/3_Historico_Cobranca.py")
    texto = _todo_o_texto(at)

    assert not at.exception
    assert "PARCEIROS ÚNICOS COBRADOS" in texto
    assert "3 registro(s)" in texto
