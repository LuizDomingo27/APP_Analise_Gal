# -*- coding: utf-8 -*-
"""
Testes da camada de Histórico de Defeitos (src/data/historico_defeitos.py):
leitura (load_historico), append diário com deduplicação por data
(append_historico), contagem de fornecedores (get_supplier_counts) e
correção de nome de fornecedor (rename_supplier).

Cobre também os caminhos de exceção (planilha inválida, valores vazios)
para garantir que a camada nunca deixe o app quebrar.
"""

import io

import pandas as pd
import pytest
from sqlalchemy import text

import src.data.database as db
import src.data.historico_defeitos as hd
from src.config.settings import COLS


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Isola a camada de histórico num SQLite temporário para cada teste."""
    db_path = tmp_path / "test_historico.db"
    sqlite_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setattr(db, "_database_url", lambda: sqlite_url)
    db.get_engine.clear()
    db.create_tables.clear()
    hd.load_historico.clear()
    hd.get_supplier_counts.clear()
    db.create_tables()
    yield db_path
    db.get_engine.clear()
    db.create_tables.clear()
    hd.load_historico.clear()
    hd.get_supplier_counts.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(date_str, supplier="Fornecedor A", qtd=10, valor=50.0, defect="PONTO ESTOURADO"):
    """Monta um registro completo (todas as colunas exigidas pela planilha)."""
    return {
        COLS["date"]:        date_str,
        COLS["order"]:       "OM-100",
        COLS["material"]:    "TECIDO X",
        COLS["supplier"]:    supplier,
        COLS["quantity"]:    qtd,
        COLS["location"]:    "MANGA",
        COLS["defect"]:      defect,
        COLS["real_cut"]:    "5",
        COLS["pct_remonte"]: 0.12,
        COLS["key"]:         "CHV-1",
        COLS["process_time"]: "00:10",
        COLS["minutes"]:     5.0,
        COLS["value_brl"]:   valor,
        COLS["status"]:      "Pendente",
    }


def _make_xlsx(rows: list[dict]) -> io.BytesIO:
    """Gera um .xlsx em memória com um objeto file-like que expõe .read()."""
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf


def _count() -> int:
    with db.get_connection() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM historico_defeitos")).fetchone()[0]


# ── load_historico ────────────────────────────────────────────────────────────

def test_load_historico_returns_none_when_empty(temp_db):
    assert hd.load_historico() is None


def test_load_historico_self_heals_when_table_missing(temp_db):
    """
    Regressão: se a tabela não existir (cache de create_tables preso a um
    schema antigo após hot-reload), load_historico deve recriá-la via
    _ensure_schema e retornar None — SEM vazar traceback para a UI.
    """
    with db.get_connection() as conn:
        conn.execute(text("DROP TABLE historico_defeitos"))
        conn.commit()
    hd.load_historico.clear()

    # Não deve levantar; retorna None e recria a tabela silenciosamente.
    assert hd.load_historico() is None
    with db.get_connection() as conn:
        conn.execute(text("SELECT * FROM historico_defeitos"))  # existe de novo


def test_load_historico_returns_rows_after_append(temp_db):
    hd.append_historico(_make_xlsx([_row("2026-07-01")]))
    hd.load_historico.clear()

    df = hd.load_historico()
    assert df is not None
    assert len(df) == 1
    assert df.iloc[0][COLS["supplier"]] == "Fornecedor A"
    # 'id' interno nunca vaza para a UI
    assert "id" not in df.columns
    # data volta como datetime tipada
    assert pd.api.types.is_datetime64_any_dtype(df[COLS["date"]])


# ── append_historico ──────────────────────────────────────────────────────────

def test_append_historico_inserts_new_rows(temp_db):
    result = hd.append_historico(_make_xlsx([_row("2026-07-01"), _row("2026-07-02")]))
    assert result is not None
    assert result["added"] == 2
    assert result["duplicates"] == 0
    assert result["total"] == 2
    assert _count() == 2


def test_append_historico_deduplicates_existing_dates(temp_db):
    hd.append_historico(_make_xlsx([_row("2026-07-01")]))
    # Reenvia a mesma data + uma data nova
    result = hd.append_historico(_make_xlsx([_row("2026-07-01"), _row("2026-07-03")]))
    assert result["added"] == 1
    assert result["duplicates"] == 1
    assert result["total"] == 2


def test_append_historico_never_deletes_previous_data(temp_db):
    hd.append_historico(_make_xlsx([_row("2026-07-01", supplier="Antigo")]))
    hd.append_historico(_make_xlsx([_row("2026-07-05", supplier="Novo")]))

    with db.get_connection() as conn:
        suppliers = {
            r[0] for r in conn.execute(
                text('SELECT DISTINCT "FORNECEDOR" FROM historico_defeitos')
            ).fetchall()
        }
    assert suppliers == {"Antigo", "Novo"}
    assert _count() == 2


def test_append_historico_returns_none_on_invalid_spreadsheet(temp_db):
    # Planilha sem as colunas obrigatórias → _validate levanta ValueError,
    # capturado pela camada, que retorna None (app não quebra).
    bad = io.BytesIO()
    pd.DataFrame({"coluna_irrelevante": [1, 2]}).to_excel(bad, index=False, engine="openpyxl")
    bad.seek(0)
    assert hd.append_historico(bad) is None
    assert _count() == 0


# ── get_supplier_counts ───────────────────────────────────────────────────────

def test_get_supplier_counts_groups_and_counts(temp_db):
    hd.append_historico(_make_xlsx([
        _row("2026-07-01", supplier="Fornecedor A"),
        _row("2026-07-02", supplier="Fornecedor A"),
        _row("2026-07-03", supplier="Fornecedor B"),
    ]))
    df = hd.get_supplier_counts()
    counts = dict(zip(df["valor"], df["qtd"]))
    assert counts["Fornecedor A"] == 2
    assert counts["Fornecedor B"] == 1


def test_get_supplier_counts_empty_when_no_data(temp_db):
    assert hd.get_supplier_counts().empty


# ── rename_supplier ───────────────────────────────────────────────────────────

def test_rename_supplier_updates_all_matching_rows(temp_db):
    hd.append_historico(_make_xlsx([
        _row("2026-07-01", supplier="Forncedor A"),   # grafia errada
        _row("2026-07-02", supplier="Forncedor A"),
        _row("2026-07-03", supplier="Fornecedor B"),
    ]))
    affected = hd.rename_supplier("Forncedor A", "Fornecedor A")
    assert affected == 2

    df = hd.get_supplier_counts()
    counts = dict(zip(df["valor"], df["qtd"]))
    assert "Forncedor A" not in counts
    assert counts["Fornecedor A"] == 2
    assert counts["Fornecedor B"] == 1


def test_rename_supplier_raises_on_empty_new_value(temp_db):
    with pytest.raises(ValueError):
        hd.rename_supplier("Fornecedor A", "   ")


def test_rename_supplier_noop_when_names_equal(temp_db):
    hd.append_historico(_make_xlsx([_row("2026-07-01", supplier="Fornecedor A")]))
    assert hd.rename_supplier("Fornecedor A", "Fornecedor A") == 0
