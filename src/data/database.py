"""
SQLite layer — connection and schema creation.
"""

import sqlite3
from contextlib import contextmanager

from src.config.settings import DB_PATH, DATASET_DIR


@contextmanager
def get_connection():
    """Yields a sqlite3 connection with WAL journal mode enabled."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def create_tables() -> None:
    """Creates all application tables if they don't already exist. Idempotent."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS registros_defeitos (
                "DATA DE PRODUÇÃO ACABAMENTO" TEXT,
                "ORDEM MESTRE"                TEXT,
                "MATERIAL"                    TEXT,
                "FORNECEDOR"                  TEXT,
                "QUANTIDADE"                  INTEGER,
                "LOCAL"                       TEXT,
                "REMONTE"                     TEXT,
                "REAL CORTADO"                TEXT,
                "PERCENTUAL DE REMONTE"       REAL,
                "CHAVE"                       TEXT,
                "TEMPO DE PROCESSO"           TEXT,
                "MINUTOS GERADOS"             REAL,
                "VALOR DO PROCESSO BRL"       REAL,
                "STATUS_COBRANCA"             TEXT
            );

            CREATE TABLE IF NOT EXISTS historico_cobrancas (
                COD_LANCAMENTO                TEXT,
                DATA_COBRANCA                 TEXT,
                DATA_VENCIMENTO               TEXT,
                DATA_PAGAMENTO                TEXT,
                CNPJ_FORNECEDOR               TEXT,
                STATUS_COBRANCA               TEXT,
                "ORDEM MESTRE"                TEXT,
                "DATA DE PRODUÇÃO ACABAMENTO" TEXT,
                "FORNECEDOR"                  TEXT,
                "QUANTIDADE"                  INTEGER,
                "REMONTE"                     TEXT,
                "REAL CORTADO"                TEXT,
                "MINUTOS GERADOS"             REAL,
                "VALOR DO PROCESSO BRL"       REAL
            );

            CREATE TABLE IF NOT EXISTS pagamentos_concluidos (
                COD_LANCAMENTO                TEXT,
                DATA_COBRANCA                 TEXT,
                DATA_VENCIMENTO               TEXT,
                DATA_PAGAMENTO                TEXT,
                CNPJ_FORNECEDOR               TEXT,
                STATUS_COBRANCA               TEXT,
                "ORDEM MESTRE"                TEXT,
                "DATA DE PRODUÇÃO ACABAMENTO" TEXT,
                "FORNECEDOR"                  TEXT,
                "QUANTIDADE"                  INTEGER,
                "REMONTE"                     TEXT,
                "REAL CORTADO"                TEXT,
                "MINUTOS GERADOS"             REAL,
                "VALOR DO PROCESSO BRL"       REAL
            );
        """)
