# -*- coding: utf-8 -*-
"""
Testes da PÁGINA de Performance (pages/7_Performance.py).

`tests/test_performance_hardening.py` cobre os módulos de `src/performance/`.
Aqui o alvo é a página: as fronteiras de erro e o custo de banco.

O defeito que originou este arquivo: a página tinha uma única fronteira global
(`page_guard`), que por decisão de projeto só captura `DatabaseUnavailableError`.
Como `report_service` converte qualquer falha interna em `ReportGenerationError`,
e como o `st.download_button` recebe os BYTES como argumento — ou seja, o arquivo
é montado durante o render, antes de qualquer clique —, uma falha de export subia
até o topo e apagava tudo o que ainda não tinha sido desenhado. Medido com o
AppTest antes da correção: uma falha no Excel da aba Fornecedores derrubava de 37
para 21 os blocos renderizados, levando junto as abas de Ordens críticas e
Qualidade dos dados, e sem nenhuma mensagem — só o traceback cru do Streamlit.

A página roda de verdade sob o AppTest, no mesmo padrão de tests/test_user_manager_ui.py.
"""

import pandas as pd
import pytest
import streamlit as st
from streamlit.runtime.scriptrunner_utils.exceptions import RerunException, StopException
from streamlit.testing.v1 import AppTest

import src.data.historico_defeitos as hist
import src.data.loader as loader
from src.config.settings import COLS
from src.performance.domain.exceptions import ReportGenerationError
from src.performance.services import analytics_service, report_service

PAGE = "pages/7_Performance.py"
USUARIO = {"username": "auditor", "nome": "Auditor", "role": "admin"}

_COLUNAS = [
    COLS["date"], COLS["order"], COLS["supplier"], COLS["quantity"],
    COLS["defect"], COLS["real_cut"], COLS["minutes"], COLS["value_brl"],
]

BASE = pd.DataFrame(
    [
        ["01/03/2026", "OM100", "FORNECEDOR A", 10, "PONTO ESTOURADO", 500, 12.5, 80.0],
        ["03/03/2026", "OM200", "FORNECEDOR B", 90, "PONTO ESTOURADO", 300, 40.0, 300.0],
        ["10/04/2026", "OM300", "FORNECEDOR C", 2, "MANCHA", 800, 3.0, 15.0],
    ],
    columns=_COLUNAS,
)

#: Blocos de markdown de uma página inteira e saudável. Serve de linha de base:
#: uma fronteira que funciona mantém este número mesmo com uma seção quebrada.
BLOCOS_PAGINA_COMPLETA = 37


@pytest.fixture
def base_carregada(monkeypatch):
    """Serve a base em memória no lugar das duas funções cacheadas de leitura."""
    monkeypatch.setattr(hist, "load_historico", lambda: BASE.copy())
    monkeypatch.setattr(loader, "load_data_from_disk", lambda: BASE.copy())
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _abrir() -> AppTest:
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.session_state["auth_user"] = dict(USUARIO)
    return at.run()


def _quebrar(monkeypatch, alvo, atributo: str, erro: Exception) -> None:
    def _falha(*args, **kwargs):
        raise erro

    monkeypatch.setattr(alvo, atributo, staticmethod(_falha))


# ── Fronteira por seção ───────────────────────────────────────────────────────

def test_pagina_saudavel_nao_avisa_nada(base_carregada):
    at = _abrir()
    assert not at.exception
    assert len(at.tabs) == 4
    assert len(at.warning) == 0
    assert len(at.markdown) == BLOCOS_PAGINA_COMPLETA


def test_falha_no_excel_do_ranking_nao_derruba_a_pagina(base_carregada, monkeypatch):
    """O caso que motivou a correção: antes dela, sobravam 21 dos 37 blocos."""
    _quebrar(
        monkeypatch, report_service.SupplierExportService, "build_excel",
        ReportGenerationError("Não foi possível gerar o Excel de fornecedores."),
    )
    at = _abrir()

    assert not at.exception, "a falha de export vazou como traceback cru"
    assert len(at.tabs) == 4
    assert len(at.markdown) == BLOCOS_PAGINA_COMPLETA, (
        "a falha de export apagou seções que não têm relação com ela"
    )
    assert any("Excel do ranking" in aviso.value for aviso in at.warning)


def test_falha_no_pdf_de_ordens_criticas_nao_derruba_a_pagina(base_carregada, monkeypatch):
    _quebrar(
        monkeypatch, report_service.PdfReportService, "build",
        ReportGenerationError("Não foi possível gerar o PDF para os filtros atuais."),
    )
    at = _abrir()

    assert not at.exception
    assert len(at.markdown) == BLOCOS_PAGINA_COMPLETA
    assert any("ordens críticas" in aviso.value for aviso in at.warning)


def test_falha_inesperada_numa_aba_preserva_as_outras(base_carregada, monkeypatch):
    """Não é só export: qualquer erro de uma aba fica contido nela."""
    _quebrar(
        monkeypatch, analytics_service.AnalyticsService, "metrics",
        RuntimeError("falha inesperada no cálculo de métricas"),
    )
    at = _abrir()

    assert not at.exception
    assert len(at.tabs) == 4, "as demais abas sumiram junto com a que falhou"
    assert any("Visão geral" in aviso.value for aviso in at.warning)
    # A aba quebrada perde o próprio conteúdo, mas as outras três continuam.
    assert len(at.markdown) > BLOCOS_PAGINA_COMPLETA / 2


# ── A fronteira não pode engolir o control-flow do Streamlit ──────────────────

def _carregar_helpers() -> dict:
    """Executa o módulo da página SEM a chamada final a `main()`.

    A página é um script: importá-la normalmente renderizaria tudo. Aqui só
    interessam os helpers de fronteira.
    """
    fonte = open(PAGE, encoding="utf-8").read().rsplit("\nmain()", 1)[0]
    espaco: dict = {}
    exec(compile(fonte, PAGE, "exec"), espaco)  # noqa: S102 — script da própria app
    return espaco


@pytest.mark.parametrize("controle", [StopException("stop"), RerunException("rerun")])
def test_secao_deixa_passar_o_control_flow_do_streamlit(controle):
    """`st.stop()`/`st.rerun()` não podem ser capturados — quebraria login e botões.

    Elas herdam de `BaseException`, então `except Exception` já as deixa passar;
    este teste existe para que uma futura troca por `except BaseException` — ou um
    `raise` mal colocado — não passe despercebida.
    """
    _section = _carregar_helpers()["_section"]

    with pytest.raises(type(controle)):
        with _section("teste"):
            raise controle


def test_secao_contem_erro_comum():
    _section = _carregar_helpers()["_section"]

    with _section("teste"):  # não pode levantar
        raise ValueError("erro de render")


# ── Frugalidade de consultas ao banco ────────────────────────────────────────

def test_pagina_nao_abre_consulta_propria(monkeypatch):
    """A página inteira custa UMA leitura — a mesma que já serve o Histórico.

    Instrumenta ABAIXO do `@st.cache_data` (troca o `read_sql`, não a função
    cacheada), senão o próprio teste destruiria o cache que quer medir.
    """
    consultas: list[str] = []

    class _Conexao:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _espiao(query, conn, *args, **kwargs):
        consultas.append(str(query))
        completa = BASE.copy()
        for chave, coluna in COLS.items():
            if coluna not in completa.columns:
                completa[coluna] = "" if chave in {"location", "key", "status"} else 0
        return completa

    monkeypatch.setattr(hist, "_ensure_schema", lambda: None)
    monkeypatch.setattr(hist, "get_connection", lambda: _Conexao())
    monkeypatch.setattr(hist.pd, "read_sql", _espiao)
    st.cache_data.clear()

    at = _abrir()
    assert not at.exception
    assert len(consultas) == 1

    # Mexer nos filtros é tudo em memória: nenhuma consulta nova.
    at.slider(key="perf_target").set_value(95).run()
    at.multiselect(key="perf_suppliers_completa").set_value(["FORNECEDOR A"]).run()
    assert len(consultas) == 1, f"a página abriu consulta própria: {consultas}"

    st.cache_data.clear()


# ── Filtros que esvaziam o recorte ───────────────────────────────────────────

def test_filtro_sem_interseccao_avisa_em_vez_de_quebrar(base_carregada):
    """FORNECEDOR C só produziu em abril; cruzado com março não sobra ordem."""
    at = _abrir()
    at.multiselect(key="perf_suppliers_completa").set_value(["FORNECEDOR C"]).run()
    at.multiselect(key="perf_months_completa").set_value(["2026-03"]).run()

    assert not at.exception
    assert len(at.tabs) == 0, "as abas foram montadas sobre um recorte vazio"
    assert any("não retornaram ordens" in aviso.value for aviso in at.warning)
