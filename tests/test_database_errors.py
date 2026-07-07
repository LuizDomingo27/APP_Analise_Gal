# -*- coding: utf-8 -*-
"""
Testes de tratamento de erro da camada de banco (src/data/database.py).

Garante a regra central: nenhuma exceção crua do psycopg2/SQLAlchemy (erro
de conexão, coluna/tabela inexistente, violação de integridade etc.) deve
escapar de `get_connection()` — tudo é traduzido para
`DatabaseUnavailableError`, com mensagem em português segura de mostrar ao
usuário final via `st.error()`, preservando a exceção técnica original em
`__cause__` para investigação nos logs.

Reproduz especificamente o cenário do bug original relatado (coluna
inexistente após migração para o Supabase) para garantir que, hoje, o app
não mostraria mais o traceback cru na tela.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

import src.auth.auth_db as auth_db
import src.data.database as db
from src.data.database import DatabaseUnavailableError, _friendly_db_message


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_errors.db"
    sqlite_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setattr(db, "_database_url", lambda: sqlite_url)
    db.get_engine.clear()
    auth_db.create_users_table.clear()
    yield db_path
    # Alguns testes substituem `db.get_engine` por um objeto simples (sem
    # cache_resource) para simular falha de conexão — nesse caso não há
    # `.clear()` para chamar, e não há nada a limpar mesmo.
    getattr(db.get_engine, "clear", lambda: None)()
    getattr(auth_db.create_users_table, "clear", lambda: None)()


# ── Tradução de mensagens: cada categoria de erro técnico vira uma mensagem
#    diferente, nenhuma delas expõe SQL, nomes de tabela/coluna ou stacktrace ──

def test_operational_error_translates_to_connection_message():
    msg = _friendly_db_message(OperationalError("stmt", {}, Exception("conn refused")))
    assert "conectar" in msg.lower()
    assert "SELECT" not in msg and "psycopg2" not in msg


def test_programming_error_translates_to_configuration_message():
    msg = _friendly_db_message(ProgrammingError("stmt", {}, Exception("UndefinedColumn")))
    assert "configuração" in msg.lower()
    assert "column" not in msg.lower()


def test_integrity_error_translates_to_conflict_message():
    msg = _friendly_db_message(IntegrityError("stmt", {}, Exception("duplicate key")))
    assert "conflita" in msg.lower() or "existente" in msg.lower()


def test_generic_sqlalchemy_error_has_safe_fallback_message():
    msg = _friendly_db_message(Exception("qualquer coisa técnica"))
    assert "erro inesperado" in msg.lower()


# ── get_connection(): nunca deixa a exceção original escapar ───────────────────

def test_get_connection_wraps_query_error_as_database_unavailable(temp_db):
    """
    Reproduz o bug original: uma query referenciando uma coluna que não
    existe na tabela (equivalente ao "UndefinedColumn" do Postgres) deve
    virar DatabaseUnavailableError, nunca a OperationalError/ProgrammingError
    crua do driver.
    """
    with db.get_connection() as conn:
        conn.execute(text("CREATE TABLE t (id integer)"))
        conn.commit()

    with pytest.raises(DatabaseUnavailableError) as excinfo:
        with db.get_connection() as conn:
            conn.execute(text("SELECT coluna_que_nao_existe FROM t"))

    # A mensagem exibida ao usuário nunca expõe nome de coluna, SQL ou o tipo
    # de exceção do driver — isso é o que importa (a categoria exata da
    # mensagem varia por dialeto: o SQLite classifica "no such column" como
    # OperationalError, enquanto o Postgres real classifica como
    # ProgrammingError/UndefinedColumn — ambas cobertas por _friendly_db_message).
    assert "coluna_que_nao_existe" not in str(excinfo.value)
    assert "SELECT" not in str(excinfo.value)
    # ...mas a causa técnica original continua disponível para os logs.
    assert excinfo.value.__cause__ is not None


def test_get_connection_wraps_connection_failure(temp_db, monkeypatch):
    class _BrokenEngine:
        def connect(self):
            raise OperationalError("connect", {}, Exception("could not connect to server"))

    monkeypatch.setattr(db, "get_engine", lambda: _BrokenEngine())

    with pytest.raises(DatabaseUnavailableError) as excinfo:
        with db.get_connection():
            pass

    assert "conectar" in str(excinfo.value).lower()


# ── auth_db.py: as funções de autenticação nunca deixam a exceção crua subir ───

def test_authenticate_raises_friendly_error_when_table_is_broken(temp_db, monkeypatch):
    """
    Simula exatamente o bug relatado: tabela de usuários com schema
    incompatível (sem a coluna que a query espera). `authenticate()` deve
    propagar DatabaseUnavailableError (mensagem amigável), não o
    ProgrammingError/UndefinedColumn cru do driver.
    """
    with db.get_connection() as conn:
        # Tabela "UserGal" criada sem a coluna "username" esperada pela query.
        conn.execute(text('CREATE TABLE "UserGal" (id integer)'))
        conn.commit()
    monkeypatch.setattr(auth_db, "create_users_table", lambda: None)

    with pytest.raises(DatabaseUnavailableError) as excinfo:
        auth_db.authenticate("luiz", "senha123")

    assert "username" not in str(excinfo.value)


def test_get_user_raises_friendly_error_on_connection_failure(temp_db, monkeypatch):
    monkeypatch.setattr(auth_db, "create_users_table", lambda: None)

    class _BrokenEngine:
        def connect(self):
            raise OperationalError("connect", {}, Exception("timeout"))

    monkeypatch.setattr(db, "get_engine", lambda: _BrokenEngine())

    with pytest.raises(DatabaseUnavailableError) as excinfo:
        auth_db.get_user("luiz")

    assert "conectar" in str(excinfo.value).lower()
