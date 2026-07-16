"""
Camada Postgres (Supabase) — engine, conexão e criação de schema.

Substitui a antiga camada SQLite. A conexão é feita via SQLAlchemy + psycopg2
apontando para o Transaction Pooler do Supabase (porta 6543). A URL vem de
`st.secrets["DATABASE_URL"]` (Streamlit Cloud / .streamlit/secrets.toml) e, como
fallback, da variável de ambiente DATABASE_URL — este fallback permite reutilizar
esta camada em scripts fora do runtime do Streamlit (ex.: migração de dados).

Todos os módulos de dados consomem `get_connection()` (um contextmanager que
entrega uma Connection SQLAlchemy 2.0) e `create_tables()`.

Tratamento de erros: `get_connection()` nunca deixa uma exceção "crua" do
psycopg2/SQLAlchemy escapar para a camada de UI. Qualquer falha (conexão
recusada, timeout, coluna/tabela inexistente, violação de constraint etc.)
é logada com detalhe técnico (visível nos logs do servidor/Streamlit Cloud)
e relançada como `DatabaseUnavailableError`, com uma mensagem já em
português e segura de mostrar ao usuário final via `st.error(str(exc))`.
"""

import hashlib
import logging
import os
from contextlib import contextmanager

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, SQLAlchemyError

logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """
    Erro de banco já traduzido para uma mensagem segura de exibir ao usuário
    final (sem SQL, nome de tabela/coluna ou stacktrace). A exceção original
    fica em `__cause__` (acessível nos logs) para investigação técnica.
    """


def _friendly_db_message(exc: Exception) -> str:
    """Mapeia exceções técnicas de banco para mensagens em português."""
    if isinstance(exc, OperationalError):
        return (
            "Não foi possível conectar ao banco de dados no momento. "
            "Verifique sua conexão com a internet e tente novamente em instantes."
        )
    if isinstance(exc, ProgrammingError):
        # Ex.: tabela/coluna inexistente — erro de configuração do sistema,
        # não algo que o usuário final possa corrigir.
        return (
            "Ocorreu um erro de configuração ao acessar os dados. "
            "Nossa equipe já foi notificada (ver logs do servidor); "
            "tente novamente mais tarde."
        )
    if isinstance(exc, IntegrityError):
        return (
            "Não foi possível concluir a operação porque ela conflita com "
            "um registro existente."
        )
    return (
        "Ocorreu um erro inesperado ao acessar os dados. "
        "Tente novamente ou contate o suporte se o problema persistir."
    )


# ── Resolução da URL de conexão ───────────────────────────────────────────────

def _database_url() -> str:
    """
    Retorna a DATABASE_URL priorizando st.secrets e caindo para a variável
    de ambiente. Lança RuntimeError com orientação se nenhuma estiver definida.
    """
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        # Fora do runtime do Streamlit st.secrets pode não existir.
        url = None
    if not url:
        url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL não configurado. Defina-o em .streamlit/secrets.toml "
            "ou na variável de ambiente DATABASE_URL. Formato esperado:\n"
            "postgresql+psycopg2://postgres.<ref>:<senha>@aws-0-<region>."
            "pooler.supabase.com:6543/postgres\n\n"
            "Rodando um script fora do Streamlit (ex.: scripts/migrate_sqlite_to_supabase.py)? "
            "O st.secrets só encontra .streamlit/secrets.toml relativo ao diretório "
            "de onde o comando foi executado — rode a partir da pasta raiz do projeto, "
            "ou passe --database-url diretamente (se o script suportar essa opção)."
        )
    return url


# ── Engine ────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_engine() -> Engine:
    """
    Cria (uma única vez por processo) o Engine SQLAlchemy para o Postgres do
    Supabase. `pool_pre_ping` descarta conexões mortas pelo pooler; o pool é
    mantido pequeno porque o Streamlit Cloud abre muitas sessões curtas.
    """
    return create_engine(
        _database_url(),
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
    )


@contextmanager
def get_connection():
    """
    Entrega uma Connection SQLAlchemy 2.0. Consumo típico:

        with get_connection() as conn:
            df = pd.read_sql(text("SELECT * FROM t"), conn)
            conn.execute(text("UPDATE t SET c = :v WHERE id = :id"), {...})
            conn.commit()          # escritas exigem commit explícito

    Qualquer `SQLAlchemyError` (conexão, sintaxe/schema, integridade etc.)
    levantado ao conectar ou durante o uso da conexão é logado com detalhe
    técnico e relançado como `DatabaseUnavailableError` — nunca deixe uma
    exceção do psycopg2/SQLAlchemy chegar crua até `st.error()`.
    """
    try:
        conn: Connection = get_engine().connect()
    except DatabaseUnavailableError:
        # Já traduzido — apenas propaga.
        raise
    except RuntimeError as exc:
        # DATABASE_URL ausente/mal configurado (_database_url). A mensagem já é
        # amigável e acionável; embrulha em DatabaseUnavailableError para que a
        # fronteira de erro das páginas a exiba sem traceback.
        logger.error("Configuração de banco indisponível: %s", exc)
        raise DatabaseUnavailableError(str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Falha ao conectar ao banco de dados")
        raise DatabaseUnavailableError(_friendly_db_message(exc)) from exc

    try:
        yield conn
    except SQLAlchemyError as exc:
        logger.exception("Erro ao executar operação no banco de dados")
        raise DatabaseUnavailableError(_friendly_db_message(exc)) from exc
    finally:
        conn.close()


# ── Concorrência ──────────────────────────────────────────────────────────────

def advisory_lock(conn: Connection, name: str) -> None:
    """
    Serializa, entre TODOS os processos do app, a seção crítica identificada por
    `name`. Use quando uma operação lê o estado do banco e decide a escrita a
    partir do que leu (ex.: "quais datas já existem?" → insere as que faltam):
    sem trava, duas sessões simultâneas leem o mesmo estado e ambas escrevem,
    duplicando os dados.

    A trava é de transação (`pg_advisory_xact_lock`): é liberada automaticamente
    no commit ou no rollback, então não vaza se a operação falhar no meio. Exige
    que `conn` já esteja numa transação — chame-a como primeira instrução do
    bloco `with get_connection()`.

    No SQLite (usado apenas nos testes) é um no-op: não existem advisory locks,
    e o SQLite já serializa escritores com uma trava global de banco.
    """
    if conn.dialect.name != "postgresql":
        return
    # pg_advisory_xact_lock exige bigint; deriva um inteiro de 64 bits estável
    # a partir do nome (hash do Python é salgado por processo — não serve).
    key = int.from_bytes(
        hashlib.blake2b(name.encode("utf-8"), digest_size=8).digest(),
        "big",
        signed=True,
    )
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


# ── Schema ────────────────────────────────────────────────────────────────────

# Nomes de coluna são mantidos EXATAMENTE como no schema SQLite original
# (com acentos, espaços e caixa alta). No Postgres isso exige aspas duplas —
# manter as aspas garante que `read_sql("SELECT *")` e `to_sql` do pandas
# preservem os mesmos nomes que o código Python já usa nos DataFrames.
#
# Diferenças relevantes vs. SQLite:
#   - `id bigserial PRIMARY KEY` adicionado às 3 tabelas de dados. Substitui o
#     `rowid` implícito do SQLite (que não existe no Postgres) usado por
#     records_editor.py para localizar linhas na edição individual.
#   - Tipos: TEXT→text, INTEGER→integer, REAL→double precision.

# DDL da tabela de histórico permanente de defeitos. Exposta como constante
# pública para que a camada src/data/historico_defeitos.py possa garantir a
# existência da tabela de forma idempotente, sem depender do cache de
# create_tables() (que, após um hot-reload do Streamlit sem reinício do
# processo, pode ficar preso a um schema antigo — sem esta tabela).
HISTORICO_DEFEITOS_DDL = """
    CREATE TABLE IF NOT EXISTS historico_defeitos (
        id                              bigserial PRIMARY KEY,
        "DATA DE PRODUÇÃO ACABAMENTO"   text,
        "ORDEM MESTRE"                  text,
        "MATERIAL"                      text,
        "FORNECEDOR"                    text,
        "QUANTIDADE"                    integer,
        "LOCAL"                         text,
        "REMONTE"                       text,
        "REAL CORTADO"                  text,
        "PERCENTUAL DE REMONTE"         double precision,
        "CHAVE"                         text,
        "TEMPO DE PROCESSO"             text,
        "MINUTOS GERADOS"               double precision,
        "VALOR DO PROCESSO BRL"         double precision,
        "STATUS_COBRANCA"               text
    )
"""


# DDL do catálogo de imagens dos defeitos. Cada tipo de defeito (REMONTE) tem
# uma imagem de referência guardada como bytea diretamente no Postgres — o
# catálogo é pequeno e fixo, então não compensa introduzir o Supabase Storage
# (pacote + SERVICE_ROLE_KEY) para isso. `chave_normalizada` é o slug do defeito
# (sem acento/espaço/prefixo "img", em maiúsculas) e serve de chave de busca:
# é por ela que a tela de consulta casa o defeito de um registro com a imagem.
# Exposta como constante pública para o _ensure_schema() idempotente da camada
# src/data/defeitos_imagens.py (mesmo motivo do HISTORICO_DEFEITOS_DDL).
DEFEITOS_IMAGENS_DDL = """
    CREATE TABLE IF NOT EXISTS defeitos_imagens (
        id                  bigserial PRIMARY KEY,
        chave_normalizada   text UNIQUE NOT NULL,
        defeito_nome        text NOT NULL,
        imagem_bytes        bytea NOT NULL,
        mime_type           text NOT NULL DEFAULT 'image/png',
        atualizado_em       timestamptz DEFAULT CURRENT_TIMESTAMP
    )
"""


# DDL da tabela da parte da cobrança absorvida pela empresa quando uma cobrança
# é dividida entre o fornecedor e a empresa. Schema espelha `devolucoes` (mesmas
# colunas) para permitir reutilizar os geradores de xlsx/HTML sem colunas extras
# quebrando o layout. STATUS_COBRANCA guarda sempre "Dividida". Exposta como
# constante pública para o _ensure_schema() idempotente de src/data/divida_dividida.py
# (mesmo motivo de HISTORICO_DEFEITOS_DDL: sobreviver a hot-reload do Streamlit).
DIVIDA_DIVIDIDA_DDL = """
    CREATE TABLE IF NOT EXISTS tb_divida_dividida (
        id                              bigserial PRIMARY KEY,
        "COD_LANCAMENTO"                text,
        "DATA_COBRANCA"                 text,
        "DATA_VENCIMENTO"               text,
        "DATA_PAGAMENTO"                text,
        "CNPJ_FORNECEDOR"               text,
        "STATUS_COBRANCA"               text,
        "ORDEM MESTRE"                  text,
        "DATA DE PRODUÇÃO ACABAMENTO"   text,
        "FORNECEDOR"                    text,
        "QUANTIDADE"                    integer,
        "REMONTE"                       text,
        "REAL CORTADO"                  text,
        "MINUTOS GERADOS"               double precision,
        "VALOR DO PROCESSO BRL"         double precision
    )
"""


_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS registros_defeitos (
        id                              bigserial PRIMARY KEY,
        "DATA DE PRODUÇÃO ACABAMENTO"   text,
        "ORDEM MESTRE"                  text,
        "MATERIAL"                      text,
        "FORNECEDOR"                    text,
        "QUANTIDADE"                    integer,
        "LOCAL"                         text,
        "REMONTE"                       text,
        "REAL CORTADO"                  text,
        "PERCENTUAL DE REMONTE"         double precision,
        "CHAVE"                         text,
        "TEMPO DE PROCESSO"             text,
        "MINUTOS GERADOS"               double precision,
        "VALOR DO PROCESSO BRL"         double precision,
        "STATUS_COBRANCA"               text
    )
    """,
    HISTORICO_DEFEITOS_DDL,
    DEFEITOS_IMAGENS_DDL,
    DIVIDA_DIVIDIDA_DDL,
    """
    CREATE TABLE IF NOT EXISTS historico_cobrancas (
        id                              bigserial PRIMARY KEY,
        "COD_LANCAMENTO"                text,
        "DATA_COBRANCA"                 text,
        "DATA_VENCIMENTO"               text,
        "DATA_PAGAMENTO"                text,
        "CNPJ_FORNECEDOR"               text,
        "STATUS_COBRANCA"               text,
        "ORDEM MESTRE"                  text,
        "DATA DE PRODUÇÃO ACABAMENTO"   text,
        "FORNECEDOR"                    text,
        "QUANTIDADE"                    integer,
        "REMONTE"                       text,
        "REAL CORTADO"                  text,
        "MINUTOS GERADOS"               double precision,
        "VALOR DO PROCESSO BRL"         double precision
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pagamentos_concluidos (
        id                              bigserial PRIMARY KEY,
        "COD_LANCAMENTO"                text,
        "DATA_COBRANCA"                 text,
        "DATA_VENCIMENTO"               text,
        "DATA_PAGAMENTO"                text,
        "CNPJ_FORNECEDOR"               text,
        "STATUS_COBRANCA"               text,
        "ORDEM MESTRE"                  text,
        "DATA DE PRODUÇÃO ACABAMENTO"   text,
        "FORNECEDOR"                    text,
        "QUANTIDADE"                    integer,
        "REMONTE"                       text,
        "REAL CORTADO"                  text,
        "MINUTOS GERADOS"               double precision,
        "VALOR DO PROCESSO BRL"         double precision
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devolucoes (
        id                              bigserial PRIMARY KEY,
        "COD_LANCAMENTO"                text,
        "DATA_COBRANCA"                 text,
        "DATA_VENCIMENTO"               text,
        "DATA_PAGAMENTO"                text,
        "CNPJ_FORNECEDOR"               text,
        "STATUS_COBRANCA"               text,
        "ORDEM MESTRE"                  text,
        "DATA DE PRODUÇÃO ACABAMENTO"   text,
        "FORNECEDOR"                    text,
        "QUANTIDADE"                    integer,
        "REMONTE"                       text,
        "REAL CORTADO"                  text,
        "MINUTOS GERADOS"               double precision,
        "VALOR DO PROCESSO BRL"         double precision
    )
    """,
]


@st.cache_resource
def create_tables() -> None:
    """
    Cria as tabelas de dados se ainda não existirem. Idempotente.

    Decorado com `@st.cache_resource` para rodar apenas uma vez por processo:
    diferente do SQLite local, cada CREATE TABLE aqui é um round-trip ao
    Postgres remoto, então não faz sentido reexecutar a cada leitura/escrita.
    """
    with get_connection() as conn:
        for stmt in _DDL_STATEMENTS:
            conn.execute(text(stmt))
        conn.commit()
