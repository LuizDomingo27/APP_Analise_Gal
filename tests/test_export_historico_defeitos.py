# -*- coding: utf-8 -*-
"""
Testes da exportação da página Histórico de Defeitos:

  · _generate_defeitos_tabela_html — relatório SÓ com tabela (sem cards de KPI).
  · _filters_description           — legenda dos filtros aplicados.
  · _xlsx_href                     — data-URI do Excel agrupado por fornecedor.
  · _render_export_bar             — fronteira defensiva.

O foco é o caminho de exceção: a barra de exportação é renderizada dentro da
linha de filtros, ANTES dos cards e dos gráficos. Uma falha ao gerar o Excel
ou o HTML da prévia deve degradar apenas a exportação — nunca derrubar a
página inteira com traceback (page_guard só captura DatabaseUnavailableError).
"""

from datetime import date

import pandas as pd
import pytest

import src.ui.historico_defeitos as hdui
from src.config.settings import COLS
from src.ui.preview import _fmt_int, _generate_defeitos_tabela_html


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def df():
    return pd.DataFrame({
        COLS["date"]:        pd.to_datetime(["2026-07-01", "2026-07-02"]),
        COLS["order"]:       [111, 222],
        COLS["supplier"]:    ["Oficina A", "Oficina B"],
        COLS["quantity"]:    [5, 9],
        COLS["location"]:    ["MANGA", "GOLA"],
        COLS["defect"]:      ["PONTO ESTOURADO", "PONTO ESTOURADO"],
        COLS["real_cut"]:    [100, 200],
        COLS["pct_remonte"]: [0.05, 0.045],
        COLS["minutes"]:     [12.5, 30.0],
        COLS["value_brl"]:   [45.5, 120.0],
    })


class _FakeSt:
    """Recorder mínimo para os widgets usados por _render_export_bar."""

    def __init__(self):
        self.captions: list[str] = []
        self.warnings: list[str] = []
        self.session_state: dict = {}

    def markdown(self, *_args, **_kwargs):
        pass

    def caption(self, text):
        self.captions.append(text)

    def warning(self, text):
        self.warnings.append(text)

    def button(self, *_args, **_kwargs):
        # O botão-gatilho da Tabela de Frequência nunca é "clicado" nos testes.
        return False


class _FakeComponents:
    def __init__(self):
        self.html_calls: list[str] = []

    def html(self, html, **_kwargs):
        self.html_calls.append(html)


@pytest.fixture
def ui(monkeypatch):
    """Substitui st e components no módulo da página por recorders."""
    fake_st, fake_comp = _FakeSt(), _FakeComponents()
    monkeypatch.setattr(hdui, "st", fake_st)
    monkeypatch.setattr(hdui, "components", fake_comp)
    # _xlsx_href é @st.cache_data: o cache é por conteúdo do DataFrame e sobrevive
    # entre testes. Como os testes trocam get_xlsx_bytes por versões que falham,
    # limpamos o cache para que cada teste exercite a geração de verdade (senão um
    # sucesso cacheado de outro teste mascara o caminho de falha).
    hdui._xlsx_href.clear()
    return fake_st, fake_comp


# ── _generate_defeitos_tabela_html: sem cards, só tabela ──────────────────────

def test_pdf_html_nao_contem_cards(df):
    html = _generate_defeitos_tabela_html(df, "Todas as oficinas")
    assert '<div class="card"' not in html
    assert 'class="cards' not in html
    assert "Resumo Executivo" not in html


def test_pdf_html_contem_a_tabela_e_os_dados(df):
    html = _generate_defeitos_tabela_html(df, "Todas as oficinas")
    assert "<table>" in html
    assert "Oficina A" in html and "Oficina B" in html
    assert "2 registros" in html


def test_pdf_html_propaga_erro_com_coluna_ausente(df):
    """Sem a coluna de valor, a geração falha — o chamador é quem protege a UI."""
    with pytest.raises(KeyError):
        _generate_defeitos_tabela_html(df.drop(columns=[COLS["value_brl"]]), "x")


# ── _fmt_int: ORDEM MESTRE / REAL CORTADO não são tipados por _cast_types ─────

@pytest.mark.parametrize("valor, esperado", [
    (1001, "1,001"),          # numérico → separador de milhar
    ("5", "5"),               # texto numérico → convertido
    (5.0, "5"),               # float → truncado
    ("OM-100", "OM-100"),     # texto livre → exibido como está (era ValueError)
    ("", "—"),                # vazio → travessão
    ("   ", "—"),
    (None, "—"),
    (float("nan"), "—"),
])
def test_fmt_int_nunca_levanta(valor, esperado):
    assert _fmt_int(valor) == esperado


def test_fmt_int_sem_separador_para_identificadores():
    assert _fmt_int(1001, sep=False) == "1001"


def test_pdf_html_com_om_textual_nao_levanta(df):
    """Regressão: int('OM-100') levantava ValueError e derrubava o relatório."""
    # Como saem do banco: object, sem cast numérico em _cast_types.
    df[COLS["order"]]    = df[COLS["order"]].astype(object)
    df[COLS["real_cut"]] = df[COLS["real_cut"]].astype(object)
    df.loc[0, COLS["order"]]    = "OM-100"
    df.loc[1, COLS["real_cut"]] = ""

    html = _generate_defeitos_tabela_html(df, "Todas as oficinas")
    assert "OM-100" in html
    assert "<td>—</td>" in html  # REAL CORTADO vazio vira travessão


# ── _filters_description ──────────────────────────────────────────────────────

def test_filters_description_com_periodo():
    desc = hdui._filters_description(
        "Oficina A", (date(2026, 7, 1), date(2026, 7, 31))
    )
    assert desc == "Oficina A · 01/07/2026 a 31/07/2026"


def test_filters_description_sem_periodo_completo():
    """Enquanto o usuário escolhe só a data inicial, date_range tem 1 item."""
    assert hdui._filters_description("Oficina A", (date(2026, 7, 1),)) == "Oficina A"
    assert hdui._filters_description("Todas as oficinas", None) == "Todas as oficinas"


# ── _xlsx_href ────────────────────────────────────────────────────────────────

def test_xlsx_href_gera_data_uri_de_planilha(df):
    href = hdui._xlsx_href(df)
    assert href.startswith(
        "data:application/vnd.openxmlformats-officedocument"
        ".spreadsheetml.sheet;base64,"
    )
    assert len(href) > 200


# ── _render_export_bar: caminhos felizes ──────────────────────────────────────

def test_export_bar_sem_filtro_mostra_so_excel_e_avisa(df, ui):
    fake_st, fake_comp = ui
    hdui._render_export_bar(df, "Todas as oficinas", None, sem_filtro=True)

    html = fake_comp.html_calls[0]
    assert "abtn-save" in html
    assert "openPreview" not in html  # botão de PDF ausente
    assert "apenas em Excel" in fake_st.captions[0]
    assert not fake_st.warnings


def test_export_bar_com_filtro_mostra_pdf_e_excel(df, ui):
    fake_st, fake_comp = ui
    hdui._render_export_bar(
        df, "Oficina A", (date(2026, 7, 1), date(2026, 7, 2)), sem_filtro=False
    )

    html = fake_comp.html_calls[0]
    assert "abtn-save" in html and "openPreview" in html
    assert "agrupados por fornecedor" in fake_st.captions[0]
    assert not fake_st.warnings


def test_export_bar_sem_registros_nao_gera_nada(df, ui):
    fake_st, fake_comp = ui
    hdui._render_export_bar(df.iloc[0:0], "Oficina A", None, sem_filtro=False)

    assert fake_comp.html_calls == []
    assert fake_st.captions == ["Nenhum registro para exportar."]


# ── _render_export_bar: caminhos de exceção ───────────────────────────────────

def _raise(exc):
    def _inner(*_args, **_kwargs):
        raise exc
    return _inner


def test_export_bar_falha_do_excel_avisa_e_nao_derruba_a_pagina(df, ui, monkeypatch):
    fake_st, fake_comp = ui
    monkeypatch.setattr(hdui, "get_xlsx_bytes", _raise(RuntimeError("openpyxl explodiu")))

    hdui._render_export_bar(df, "Oficina A", None, sem_filtro=False)  # não levanta

    assert fake_comp.html_calls == []  # nenhuma barra é renderizada
    assert "Não foi possível gerar" in fake_st.warnings[0]


def test_export_bar_falha_do_pdf_degrada_para_excel(df, ui, monkeypatch):
    """A prévia falha, mas o Excel continua disponível — sem traceback."""
    fake_st, fake_comp = ui
    monkeypatch.setattr(
        hdui, "_generate_defeitos_tabela_html", _raise(ValueError("OM não numérica"))
    )

    hdui._render_export_bar(
        df, "Oficina A", (date(2026, 7, 1), date(2026, 7, 2)), sem_filtro=False
    )

    html = fake_comp.html_calls[0]
    assert "abtn-save" in html         # Excel presente
    assert "openPreview" not in html   # PDF ausente
    assert "prévia em PDF está indisponível" in fake_st.captions[0]
    assert not fake_st.warnings


def test_export_bar_falha_do_excel_tem_precedencia_sobre_o_pdf(df, ui, monkeypatch):
    """Sem Excel não há barra alguma — nem tentamos montar a prévia."""
    fake_st, fake_comp = ui
    monkeypatch.setattr(hdui, "get_xlsx_bytes", _raise(MemoryError("dataset gigante")))

    chamou_pdf = []
    monkeypatch.setattr(
        hdui,
        "_generate_defeitos_tabela_html",
        lambda *_a, **_k: (chamou_pdf.append(True), "")[1],
    )

    hdui._render_export_bar(df, "Oficina A", None, sem_filtro=False)

    assert chamou_pdf == []
    assert fake_st.warnings
