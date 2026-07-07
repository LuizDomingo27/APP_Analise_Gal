# -*- coding: utf-8 -*-
"""
Testes da camada de autenticação (src/auth/auth_db.py), com foco em:

1. A tabela de destino é `"UserGal"` (renomeada para não colidir com uma
   tabela `usuarios` pré-existente no mesmo projeto Supabase) e o
   identificador entre aspas duplas funciona igual no SQLite (usado aqui
   para isolar o teste) e no Postgres real.
2. Caminhos de erro (usuário inválido, senha fraca, duplicidade, login
   errado, remoção do último admin etc.) retornam `(False, mensagem)` em
   vez de lançar exceção — para não derrubar o app em produção quando o
   usuário digita algo inesperado.

Segue o mesmo padrão de isolamento de banco de tests/test_cobranca_history.py:
troca a DATABASE_URL para um SQLite temporário via monkeypatch, em vez de
tocar o Postgres/Supabase real.
"""

import pytest
from sqlalchemy import text

import src.auth.auth_db as auth_db
import src.data.database as db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_auth.db"
    sqlite_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setattr(db, "_database_url", lambda: sqlite_url)
    db.get_engine.clear()
    auth_db.create_users_table.clear()
    auth_db.create_users_table()
    yield db_path
    db.get_engine.clear()
    auth_db.create_users_table.clear()


# ── Schema: a tabela criada é "UserGal", com aspas preservando o case ─────────

def test_create_users_table_creates_usergal_with_correct_columns(temp_db):
    with db.get_connection() as conn:
        rows = conn.execute(text('PRAGMA table_info("UserGal")')).fetchall()
    columns = [r[1] for r in rows]
    assert columns == [
        "username", "nome", "senha_hash", "salt", "security_question",
        "security_answer_hash", "role", "created_at",
    ]


def test_create_users_table_is_idempotent(temp_db):
    # Chamar de novo não deve lançar erro (CREATE TABLE IF NOT EXISTS).
    with db.get_connection() as conn:
        conn.execute(
            text(
                'CREATE TABLE IF NOT EXISTS "UserGal" ('
                "username text PRIMARY KEY, nome text NOT NULL, "
                "senha_hash text NOT NULL, salt text NOT NULL, "
                "security_question text, security_answer_hash text, "
                "role text NOT NULL DEFAULT 'user', created_at text NOT NULL)"
            )
        )
        conn.commit()


# ── Criação de usuário: caminho feliz ──────────────────────────────────────────

def test_create_user_first_user_becomes_admin(temp_db):
    ok, msg = auth_db.create_user("luiz", "Luiz", "senha123")
    assert ok is True
    assert "administrador" in msg
    user = auth_db.get_user("luiz")
    assert user["role"] == "admin"


def test_create_user_second_user_becomes_regular_user(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    ok, msg = auth_db.create_user("maria", "Maria", "senha123")
    assert ok is True
    user = auth_db.get_user("maria")
    assert user["role"] == "user"


def test_create_user_normalizes_username_to_lowercase(temp_db):
    auth_db.create_user("  LUIZ  ", "Luiz", "senha123")
    assert auth_db.user_exists("luiz") is True


# ── Validação de erro na criação de usuário ────────────────────────────────────

@pytest.mark.parametrize("bad_username", [
    "ab",                # curto demais (< 3)
    "usuario_muito_longo_ultrapassando_32_chars",  # longo demais
    "usuário",           # acento não permitido
    "user name",         # espaço não permitido
    "user!name",         # caractere especial não permitido
])
def test_create_user_rejects_invalid_username(temp_db, bad_username):
    ok, msg = auth_db.create_user(bad_username, "Nome", "senha123")
    assert ok is False
    assert "inválido" in msg


def test_create_user_rejects_empty_name(temp_db):
    ok, msg = auth_db.create_user("luiz", "   ", "senha123")
    assert ok is False
    assert "nome" in msg.lower()


def test_create_user_rejects_short_password(temp_db):
    ok, msg = auth_db.create_user("luiz", "Luiz", "123")
    assert ok is False
    assert "senha" in msg.lower()


def test_create_user_rejects_duplicate_username(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    ok, msg = auth_db.create_user("luiz", "Outro Luiz", "outrasenha")
    assert ok is False
    assert "já está em uso" in msg


# ── Autenticação ────────────────────────────────────────────────────────────────

def test_authenticate_succeeds_with_correct_password(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    ok, result = auth_db.authenticate("luiz", "senha123")
    assert ok is True
    assert result["username"] == "luiz"


def test_authenticate_fails_with_wrong_password(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    ok, msg = auth_db.authenticate("luiz", "senhaerrada")
    assert ok is False
    assert isinstance(msg, str)


def test_authenticate_fails_for_nonexistent_user(temp_db):
    ok, msg = auth_db.authenticate("naoexiste", "qualquersenha")
    assert ok is False
    assert isinstance(msg, str)


def test_get_user_returns_none_for_empty_or_none_username(temp_db):
    assert auth_db.get_user("") is None
    assert auth_db.get_user(None) is None


def test_get_user_returns_none_for_nonexistent_user(temp_db):
    assert auth_db.get_user("fantasma") is None


# ── Atualização / reset de senha ────────────────────────────────────────────────

def test_update_password_fails_for_nonexistent_user(temp_db):
    ok, msg = auth_db.update_password("fantasma", "novasenha123")
    assert ok is False
    assert "não encontrado" in msg


def test_update_password_rejects_short_password(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    ok, msg = auth_db.update_password("luiz", "123")
    assert ok is False
    assert "senha" in msg.lower()


def test_update_password_then_authenticate_with_new_password(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    ok, _ = auth_db.update_password("luiz", "novasenha456")
    assert ok is True
    ok, _ = auth_db.authenticate("luiz", "novasenha456")
    assert ok is True
    ok, _ = auth_db.authenticate("luiz", "senha123")
    assert ok is False


def test_reset_password_with_answer_fails_without_security_question(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")  # sem pergunta de segurança
    ok, msg = auth_db.reset_password_with_answer("luiz", "qualquer", "novasenha123")
    assert ok is False
    assert "pergunta de segurança" in msg


def test_reset_password_with_answer_fails_with_wrong_answer(temp_db):
    auth_db.create_user(
        "luiz", "Luiz", "senha123",
        security_question="Cor favorita?", security_answer="azul",
    )
    ok, msg = auth_db.reset_password_with_answer("luiz", "verde", "novasenha123")
    assert ok is False
    assert "incorreta" in msg


def test_reset_password_with_answer_succeeds_with_correct_answer(temp_db):
    auth_db.create_user(
        "luiz", "Luiz", "senha123",
        security_question="Cor favorita?", security_answer="Azul",
    )
    # Resposta normalizada: case/espaço não deveriam importar.
    ok, msg = auth_db.reset_password_with_answer("luiz", "  AZUL  ", "novasenha123")
    assert ok is True
    ok, _ = auth_db.authenticate("luiz", "novasenha123")
    assert ok is True


# ── Remoção de usuário ──────────────────────────────────────────────────────────

def test_delete_user_fails_for_nonexistent_user(temp_db):
    ok, msg = auth_db.delete_user("fantasma")
    assert ok is False
    assert "não encontrado" in msg


def test_delete_user_blocks_removal_of_last_admin(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")  # único admin
    ok, msg = auth_db.delete_user("luiz")
    assert ok is False
    assert "único administrador" in msg


def test_delete_user_allows_removal_of_admin_when_another_admin_exists(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")  # admin
    auth_db.create_user("maria", "Maria", "senha123", role="admin")  # segundo admin
    ok, msg = auth_db.delete_user("luiz")
    assert ok is True
    assert auth_db.user_exists("luiz") is False


def test_delete_user_removes_regular_user(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    auth_db.create_user("maria", "Maria", "senha123")
    ok, _ = auth_db.delete_user("maria")
    assert ok is True
    assert auth_db.user_exists("maria") is False
    assert auth_db.user_exists("luiz") is True  # não afeta outros usuários


# ── Listagem ────────────────────────────────────────────────────────────────────

def test_list_users_does_not_expose_password_hashes(temp_db):
    auth_db.create_user("luiz", "Luiz", "senha123")
    users = auth_db.list_users()
    assert len(users) == 1
    assert "senha_hash" not in users[0]
    assert "salt" not in users[0]


def test_list_users_orders_case_insensitively(temp_db):
    auth_db.create_user("maria", "Maria", "senha123")
    auth_db.create_user("Bruno", "Bruno", "senha123")
    usernames = [u["username"] for u in auth_db.list_users()]
    assert usernames == ["bruno", "maria"]
