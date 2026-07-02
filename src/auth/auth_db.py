# -*- coding: utf-8 -*-
"""
Camada de dados de autenticação — tabela `usuarios`.

Vive no mesmo arquivo SQLite da aplicação (dataset/analise_gal.db) para
persistir junto com o restante da base via o mesmo mecanismo de sync com
o GitHub. As senhas NUNCA são armazenadas em texto puro: guardamos apenas
o hash PBKDF2-HMAC-SHA256 com salt aleatório por usuário. A resposta da
pergunta de segurança também é armazenada como hash.

Escopo: este módulo só toca a tabela `usuarios`. Não lê nem escreve em
registros_defeitos, historico_cobrancas ou pagamentos_concluidos.
"""

import hashlib
import re
import secrets
from datetime import datetime

from src.config.settings import DB_PATH
from src.data.database import get_connection
from src.data.github_sync import push_db_to_github

# ── Parâmetros de hashing ─────────────────────────────────────────────────────
_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16

# ── Regras de validação ───────────────────────────────────────────────────────
_MIN_PASSWORD_LEN = 6
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


# ── Hashing helpers ───────────────────────────────────────────────────────────

def _new_salt() -> str:
    return secrets.token_hex(_SALT_BYTES)


def _hash_secret(raw: str, salt_hex: str) -> str:
    """PBKDF2-HMAC-SHA256 de `raw` com o salt informado (hex → hex)."""
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return dk.hex()


def _verify_secret(raw: str, salt_hex: str, expected_hash: str) -> bool:
    if not expected_hash:
        return False
    candidate = _hash_secret(raw, salt_hex)
    return secrets.compare_digest(candidate, expected_hash)


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _normalize_answer(answer: str) -> str:
    """Normaliza a resposta de segurança (case/espaços) para comparação estável."""
    return " ".join((answer or "").strip().lower().split())


# ── Schema ────────────────────────────────────────────────────────────────────

def create_users_table() -> None:
    """Cria a tabela `usuarios` se ainda não existir. Idempotente."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                username             TEXT PRIMARY KEY,
                nome                 TEXT NOT NULL,
                senha_hash           TEXT NOT NULL,
                salt                 TEXT NOT NULL,
                security_question    TEXT,
                security_answer_hash TEXT,
                role                 TEXT NOT NULL DEFAULT 'user',
                created_at           TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _sync() -> None:
    """Persiste o banco no GitHub (mesmo mecanismo do restante do app)."""
    push_db_to_github(DB_PATH)


# ── Consultas ─────────────────────────────────────────────────────────────────

def count_users() -> int:
    create_users_table()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()
    return int(row[0]) if row else 0


def get_user(username: str) -> dict | None:
    """Retorna o registro do usuário como dict, ou None se não existir."""
    uname = normalize_username(username)
    if not uname:
        return None
    create_users_table()
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT username, nome, senha_hash, salt, security_question, "
            "security_answer_hash, role, created_at "
            "FROM usuarios WHERE username = ?",
            (uname,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    keys = [
        "username", "nome", "senha_hash", "salt", "security_question",
        "security_answer_hash", "role", "created_at",
    ]
    return dict(zip(keys, row))


def list_users() -> list[dict]:
    """Lista usuários (sem hashes) para exibição no painel de gestão."""
    create_users_table()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT username, nome, role, created_at "
            "FROM usuarios ORDER BY username COLLATE NOCASE"
        ).fetchall()
    return [
        {"username": r[0], "nome": r[1], "role": r[2], "created_at": r[3]}
        for r in rows
    ]


def user_exists(username: str) -> bool:
    return get_user(username) is not None


# ── Escrita ───────────────────────────────────────────────────────────────────

def create_user(
    username: str,
    nome: str,
    password: str,
    security_question: str = "",
    security_answer: str = "",
    role: str | None = None,
) -> tuple[bool, str]:
    """
    Cria um novo usuário. O primeiro usuário criado vira 'admin'
    automaticamente. Retorna (ok, mensagem).
    """
    uname = normalize_username(username)
    nome = (nome or "").strip()

    if not _USERNAME_RE.match(uname):
        return False, (
            "Usuário inválido. Use 3–32 caracteres: letras minúsculas, "
            "números, ponto, hífen ou underscore."
        )
    if not nome:
        return False, "Informe o nome do usuário."
    if len(password or "") < _MIN_PASSWORD_LEN:
        return False, f"A senha deve ter ao menos {_MIN_PASSWORD_LEN} caracteres."

    create_users_table()

    if user_exists(uname):
        return False, "Este nome de usuário já está em uso."

    # Primeiro usuário do sistema torna-se administrador.
    effective_role = role or ("admin" if count_users() == 0 else "user")

    salt = _new_salt()
    senha_hash = _hash_secret(password, salt)
    answer_hash = (
        _hash_secret(_normalize_answer(security_answer), salt)
        if security_answer else ""
    )

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO usuarios "
            "(username, nome, senha_hash, salt, security_question, "
            " security_answer_hash, role, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uname, nome, senha_hash, salt,
                (security_question or "").strip(), answer_hash,
                effective_role, datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()

    _sync()
    return True, (
        f"Usuário '{uname}' criado com sucesso"
        + (" como administrador." if effective_role == "admin" else ".")
    )


def authenticate(username: str, password: str) -> tuple[bool, object]:
    """
    Verifica credenciais. Retorna (True, user_dict) em sucesso ou
    (False, mensagem_de_erro) em falha.
    """
    user = get_user(username)
    if user is None:
        return False, "Usuário ou senha inválidos."
    if not _verify_secret(password or "", user["salt"], user["senha_hash"]):
        return False, "Usuário ou senha inválidos."
    return True, user


def update_password(username: str, new_password: str) -> tuple[bool, str]:
    """Redefine a senha de um usuário existente (gera novo salt)."""
    user = get_user(username)
    if user is None:
        return False, "Usuário não encontrado."
    if len(new_password or "") < _MIN_PASSWORD_LEN:
        return False, f"A senha deve ter ao menos {_MIN_PASSWORD_LEN} caracteres."

    salt = _new_salt()
    senha_hash = _hash_secret(new_password, salt)

    with get_connection() as conn:
        conn.execute(
            "UPDATE usuarios SET senha_hash = ?, salt = ? WHERE username = ?",
            (senha_hash, salt, user["username"]),
        )
        conn.commit()

    _sync()
    return True, "Senha redefinida com sucesso."


def get_security_question(username: str) -> str | None:
    """Retorna a pergunta de segurança do usuário, se houver."""
    user = get_user(username)
    if user is None:
        return None
    return user["security_question"] or None


def reset_password_with_answer(
    username: str, security_answer: str, new_password: str
) -> tuple[bool, str]:
    """
    Redefine a senha validando a resposta da pergunta de segurança.
    Como o reset gera novo salt, a resposta é re-hasheada com o novo salt.
    """
    user = get_user(username)
    if user is None:
        return False, "Usuário não encontrado."
    if not user["security_answer_hash"]:
        return False, (
            "Este usuário não configurou uma pergunta de segurança. "
            "Peça a um administrador para redefinir a senha."
        )
    if not _verify_secret(
        _normalize_answer(security_answer), user["salt"], user["security_answer_hash"]
    ):
        return False, "Resposta de segurança incorreta."
    if len(new_password or "") < _MIN_PASSWORD_LEN:
        return False, f"A senha deve ter ao menos {_MIN_PASSWORD_LEN} caracteres."

    salt = _new_salt()
    senha_hash = _hash_secret(new_password, salt)
    # Re-hash da resposta com o novo salt para manter o reset funcional depois.
    answer_hash = _hash_secret(_normalize_answer(security_answer), salt)

    with get_connection() as conn:
        conn.execute(
            "UPDATE usuarios SET senha_hash = ?, salt = ?, "
            "security_answer_hash = ? WHERE username = ?",
            (senha_hash, salt, answer_hash, user["username"]),
        )
        conn.commit()

    _sync()
    return True, "Senha redefinida com sucesso. Você já pode entrar."


def delete_user(username: str) -> tuple[bool, str]:
    """Remove um usuário. Não permite remover o último administrador."""
    user = get_user(username)
    if user is None:
        return False, "Usuário não encontrado."

    if user["role"] == "admin":
        create_users_table()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM usuarios WHERE role = 'admin'"
            ).fetchone()
        if row and int(row[0]) <= 1:
            return False, "Não é possível remover o único administrador."

    with get_connection() as conn:
        conn.execute("DELETE FROM usuarios WHERE username = ?", (user["username"],))
        conn.commit()

    _sync()
    return True, f"Usuário '{user['username']}' removido."
