# -*- coding: utf-8 -*-
"""
Testes da página Gerenciar Usuários (src/ui/user_manager.py).

Foco no fluxo de exclusão, que já quebrou uma vez em silêncio: o retorno do
botão 🗑️ era ignorado, então nada marcava a pendência na sessão e o painel de
confirmação — que existia no código — nunca aparecia. Nenhum erro era exibido;
o botão simplesmente não fazia nada.

Aqui a página roda de verdade sob o AppTest do Streamlit (widgets, reruns e
session_state reais) contra um SQLite temporário, no mesmo padrão de isolamento
de tests/test_auth_db.py.
"""

import pytest
from streamlit.testing.v1 import AppTest

import src.auth.auth_db as auth_db
import src.data.database as db

ADMIN = {"username": "admin.teste", "nome": "Admin Teste", "role": "admin"}


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_user_manager.db"
    sqlite_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setattr(db, "_database_url", lambda: sqlite_url)
    db.get_engine.clear()
    auth_db.create_users_table.clear()
    auth_db.list_users.clear()
    auth_db.create_users_table()

    # O primeiro usuário criado vira admin automaticamente.
    auth_db.create_user("admin.teste", "Admin Teste", "senha123")
    auth_db.create_user("maria.silva", "Maria Silva", "senha123", role="user")
    auth_db.list_users.clear()

    yield db_path

    db.get_engine.clear()
    auth_db.create_users_table.clear()
    auth_db.list_users.clear()


def _pagina() -> None:
    from src.ui.user_manager import render_user_manager_page

    render_user_manager_page()


def _abrir(**estado) -> AppTest:
    at = AppTest.from_function(_pagina, default_timeout=60)
    at.session_state["auth_user"] = dict(ADMIN)
    for chave, valor in estado.items():
        at.session_state[chave] = valor
    return at.run()


def _botao_lixeira(at: AppTest, username: str):
    for botao in at.button:
        if botao.key and botao.key.startswith(f"del_btn_{username}_"):
            return botao
    raise AssertionError(f"botão de excluir de {username} não encontrado")


def _html(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_lixeira_do_usuario_aparece_para_os_outros_mas_nao_para_si(temp_db):
    at = _abrir()

    assert _botao_lixeira(at, "maria.silva") is not None
    with pytest.raises(AssertionError):
        _botao_lixeira(at, "admin.teste")  # de si mesmo o admin não vê botão
    assert not at.exception


def test_lixeira_pede_confirmacao_em_vez_de_excluir_na_hora(temp_db):
    at = _abrir()

    _botao_lixeira(at, "maria.silva").click().run()

    assert at.session_state["confirm_delete"] == "maria.silva"
    assert "Confirmação de Exclusão" in _html(at)
    # Nada foi removido ainda — o clique só abre a confirmação.
    assert auth_db.get_user("maria.silva") is not None
    assert not at.exception


def test_confirmar_remove_o_usuario_de_fato(temp_db):
    at = _abrir()
    _botao_lixeira(at, "maria.silva").click().run()

    at.button(key="confirm_del_yes").click().run()

    assert auth_db.get_user("maria.silva") is None
    assert "confirm_delete" not in at.session_state
    assert "removido" in at.success[0].value  # feedback exibido no rerun
    assert not at.exception


def test_cancelar_mantem_o_usuario(temp_db):
    at = _abrir()
    _botao_lixeira(at, "maria.silva").click().run()

    at.button(key="confirm_del_no").click().run()

    assert auth_db.get_user("maria.silva") is not None
    assert "confirm_delete" not in at.session_state
    assert "Confirmação de Exclusão" not in _html(at)
    assert not at.exception


def test_recusa_do_banco_nao_derruba_a_pagina(temp_db):
    """Só existe um admin: remover a si mesmo é recusado com mensagem."""
    at = _abrir(confirm_delete="admin.teste")

    at.button(key="confirm_del_yes").click().run()

    assert auth_db.get_user("admin.teste") is not None
    assert "único administrador" in at.error[0].value
    assert not at.exception


def test_pendencia_de_usuario_ja_removido_e_descartada(temp_db):
    """Exclusão feita em outra sessão não pode deixar a confirmação órfã."""
    at = _abrir(confirm_delete="fantasma")

    assert "confirm_delete" not in at.session_state
    assert "Confirmação de Exclusão" not in _html(at)
    assert not at.exception
