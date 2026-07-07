# -*- coding: utf-8 -*-
"""
Migração one-time: dataset/analise_gal.db (SQLite) -> Postgres (Supabase).

Lê as 4 tabelas do SQLite local e insere no Postgres apontado por
DATABASE_URL (st.secrets ou variável de ambiente — mesma resolução usada
pelo app, ver src/data/database.py). Idempotente por padrão: se a tabela de
destino já tiver linhas, pula e avisa, em vez de duplicar. Use --force para
sobrescrever esse comportamento (ex.: depois de um teste em banco vazio).

Uso:
    python scripts/migrate_sqlite_to_supabase.py
    python scripts/migrate_sqlite_to_supabase.py --source dataset/analise_gal.db
    python scripts/migrate_sqlite_to_supabase.py --force   # ignora a checagem de "já tem dados"

Pré-requisito: DATABASE_URL configurada em .streamlit/secrets.toml (ou env)
apontando para o Transaction Pooler do Supabase (porta 6543).
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.data.database as database  # noqa: E402
from src.data.database import create_tables, get_connection  # noqa: E402
from src.auth.auth_db import create_users_table  # noqa: E402

# Tabelas de dados "normais" — schema criado por create_tables(), sempre com
# `id bigserial PRIMARY KEY` extra no destino (ausente na origem SQLite).
_DATA_TABLES = ["registros_defeitos", "historico_cobrancas", "pagamentos_concluidos"]

# Tabela de origem no SQLite continua se chamando "usuarios" — só o destino no
# Postgres foi renomeado para "UserGal" (ver src/auth/auth_db.py) para não
# colidir com outra tabela `usuarios` já existente nesse projeto Supabase.
# Tem PK própria (username) e é tratada à parte: nunca reinserida se o
# username já existir no destino, para não sobrescrever contas já criadas
# diretamente no Postgres após o corte.
_USERS_TABLE = "usuarios"


def _read_sqlite_table(sqlite_conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    try:
        return pd.read_sql(f"SELECT * FROM {table}", sqlite_conn)
    except pd.errors.DatabaseError:
        return pd.DataFrame()


def _dest_row_count(table: str) -> int:
    with get_connection() as conn:
        row = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
    return int(row[0]) if row else 0


def migrate_data_table(sqlite_conn: sqlite3.Connection, table: str, force: bool) -> dict:
    df = _read_sqlite_table(sqlite_conn, table)
    origin_count = len(df)

    existing = _dest_row_count(table)
    if existing > 0 and not force:
        return {
            "table": table, "origin": origin_count, "skipped": True,
            "dest_before": existing, "dest_after": existing,
        }

    if not df.empty:
        # `id` é gerado pelo bigserial do Postgres; a origem SQLite não tem
        # essa coluna, então não há conflito — cada linha ganha um id novo.
        with get_connection() as conn:
            df.to_sql(table, conn, if_exists="append", index=False)
            conn.commit()

    dest_after = _dest_row_count(table)
    return {
        "table": table, "origin": origin_count, "skipped": False,
        "dest_before": existing, "dest_after": dest_after,
    }


def migrate_users(sqlite_conn: sqlite3.Connection) -> dict:
    df = _read_sqlite_table(sqlite_conn, _USERS_TABLE)
    inserted, already_existed = 0, 0

    with get_connection() as conn:
        for _, row in df.iterrows():
            exists = conn.execute(
                text('SELECT 1 FROM "UserGal" WHERE username = :u'),
                {"u": row["username"]},
            ).fetchone()
            if exists:
                already_existed += 1
                continue
            conn.execute(
                text(
                    'INSERT INTO "UserGal" '
                    "(username, nome, senha_hash, salt, security_question, "
                    " security_answer_hash, role, created_at) "
                    "VALUES (:username, :nome, :senha_hash, :salt, :sq, :sah, :role, :created_at)"
                ),
                {
                    "username": row["username"], "nome": row["nome"],
                    "senha_hash": row["senha_hash"], "salt": row["salt"],
                    "sq": row.get("security_question") or "",
                    "sah": row.get("security_answer_hash") or "",
                    "role": row["role"], "created_at": row["created_at"],
                },
            )
            inserted += 1
        conn.commit()

    return {"origin": len(df), "inserted": inserted, "already_existed": already_existed}


def check_admin() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            text('SELECT username FROM "UserGal" WHERE role = \'admin\'')
        ).fetchall()
    return [r[0] for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", default=str(ROOT / "dataset" / "analise_gal.db"),
        help="Caminho do arquivo SQLite de origem (default: dataset/analise_gal.db)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Migra mesmo se a tabela de destino já tiver linhas (duplica dados!)",
    )
    parser.add_argument(
        "--database-url", default=None,
        help=(
            "DATABASE_URL do Postgres/Supabase, passada direto na linha de comando. "
            "Tem prioridade sobre secrets.toml e sobre a variável de ambiente — "
            "use isso se o script não estiver achando sua configuração automaticamente "
            "(ex.: rodando de fora da pasta raiz do projeto)."
        ),
    )
    args = parser.parse_args()

    if args.database_url:
        # Bypassa completamente a resolução via st.secrets/env de database.py —
        # útil quando o .streamlit/secrets.toml não é encontrado por causa do
        # diretório de onde o script foi executado.
        database._database_url = lambda: args.database_url

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"❌ Arquivo SQLite não encontrado: {source_path}")
        return 1

    print(f"Origem: {source_path}")
    print("Criando/validando schema no Postgres (Supabase)...")
    create_tables()
    create_users_table()

    sqlite_conn = sqlite3.connect(str(source_path))
    try:
        print("\n── Tabelas de dados ─────────────────────────────────────────")
        results = []
        for table in _DATA_TABLES:
            r = migrate_data_table(sqlite_conn, table, force=args.force)
            results.append(r)
            if r["skipped"]:
                print(
                    f"  [SKIP] {table}: destino já tem {r['dest_before']} linha(s). "
                    f"Use --force para sobrescrever. (origem tinha {r['origin']})"
                )
            else:
                status = "✅" if r["dest_after"] == r["dest_before"] + r["origin"] else "⚠️"
                print(
                    f"  {status} {table}: {r['origin']} linha(s) na origem -> "
                    f"destino {r['dest_before']} → {r['dest_after']}"
                )

        print("\n── Usuários ──────────────────────────────────────────────────")
        u = migrate_users(sqlite_conn)
        print(
            f"  usuarios -> UserGal: {u['origin']} na origem — "
            f"{u['inserted']} inserido(s), {u['already_existed']} já existiam no destino"
        )
    finally:
        sqlite_conn.close()

    print("\n── Validação de contagens (origem SQLite vs. destino Postgres) ──")
    all_ok = True
    conn_check = sqlite3.connect(str(source_path))
    try:
        for table in _DATA_TABLES:
            origin_total = conn_check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            dest_total = _dest_row_count(table)
            ok = origin_total == dest_total
            all_ok &= ok
            marker = "✅" if ok else "❌"
            print(f"  {marker} {table}: origem={origin_total}  destino={dest_total}")
    finally:
        conn_check.close()

    print("\n── Administradores no destino ───────────────────────────────────")
    admins = check_admin()
    if admins:
        print(f"  ✅ {len(admins)} admin(s): {', '.join(admins)}")
    else:
        print("  ❌ Nenhum usuário com role='admin' encontrado no destino!")
        all_ok = False

    print()
    if all_ok:
        print("✅ Migração validada. Próximo passo (Fase 5 do plano): testar login, "
              "upload de planilha, lançar/pagar cobrança e downloads xlsx apontando "
              "para este mesmo Postgres antes do corte em produção.")
        return 0
    else:
        print("⚠️ Alguma contagem ou checagem não bateu — revise antes de prosseguir "
              "para o corte (Fase 6).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
