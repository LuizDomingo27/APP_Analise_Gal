# Plano de Migração: SQLite + GitHub-sync → Supabase (Postgres)

**Data:** 2026-07-06
**Decisões travadas:**
- **Acesso a dados:** conexão Postgres direta (SQLAlchemy + psycopg2 no pooler do Supabase). *Não* usar o cliente `supabase-py`/PostgREST (a "chave token" anon/service_role) — o código é 100% pandas + SQL cru e encaixa quase 1:1 na conexão direta.
- **Autenticação:** manter a auth própria (tabela `UserGal`, PBKDF2 + pergunta de segurança), apenas movida para o Postgres. Supabase Auth (GoTrue) fica para uma fase futura opcional.

---

## 1. Por que migrar

O modelo atual persiste os dados fazendo **commit do arquivo `.db` inteiro no GitHub** a cada escrita (`push_db_to_github`). Problemas:
- **Condição de corrida:** dois usuários escrevendo ~ao mesmo tempo geram commits conflitantes; o último a subir sobrescreve o outro (perda de dados silenciosa).
- **Latência:** cada escrita = uma chamada à API do GitHub.
- **Segurança:** hashes de senha versionados no repo → obriga repo privado.
- **Escala:** o `.db` cresce e é reenviado inteiro toda vez.

Postgres resolve tudo isso nativamente: escritas concorrentes transacionais, persistência real, sem sync manual.

## 2. Estado atual (o que muda)

| Arquivo | Papel hoje | Ação na migração |
|---|---|---|
| `src/data/database.py` | `get_connection()` (sqlite3) + `create_tables()` | **Reescrever** para engine Postgres |
| `src/data/github_sync.py` | `push_db_to_github()` após cada escrita | **Remover** (Postgres persiste sozinho) |
| `src/data/loader.py` | registros_defeitos (read/append) | Trocar placeholders/dialeto |
| `src/data/cobranca_history.py` | historico_cobrancas | Trocar placeholders/dialeto |
| `src/data/payment_history.py` | pagamentos_concluidos | Trocar placeholders/dialeto |
| `src/data/records_editor.py` | edição por **`rowid`** | **Crítico:** `rowid` não existe no Postgres → usar PK `id` |
| `src/auth/auth_db.py` | tabela `UserGal` | Trocar placeholders/dialeto; remover `_sync()` |
| `src/config/settings.py` | `DB_PATH`, `DATASET_DIR` | Adicionar leitura de `DATABASE_URL` dos secrets |
| `requirements.txt` | — | `+sqlalchemy`, `+psycopg2-binary`; remover `PyGithub` |

Contagem: ~101 chamadas a `get_connection/read_sql/to_sql/execute` em 7 arquivos; `rowid` em 12 pontos; placeholders `?` e `COLLATE NOCASE` espalhados.

## 3. Tradução de schema SQLite → Postgres

Postgres suporta identificadores com aspas (`"DATA DE PRODUÇÃO ACABAMENTO"`) — **mantemos os nomes de coluna como estão**, então os SQLs com aspas continuam válidos. Pontos de atenção:

- **Tipos:** `TEXT`→`text`, `INTEGER`→`integer`, `REAL`→`double precision`.
- **`rowid` (bloqueador):** `registros_defeitos` não tem PK. Adicionar `id bigserial PRIMARY KEY`. O `ctid` do Postgres **não** é estável (muda em VACUUM/UPDATE) — não serve de substituto.
- **`COLLATE NOCASE`:** não existe no Postgres. Trocar `ORDER BY col COLLATE NOCASE` por `ORDER BY LOWER(col)`.
- **Placeholders:** `?` (sqlite) → `%s` (psycopg2) ou `:nome` (SQLAlchemy `text()`).
- **`to_sql(if_exists="append")`:** funciona com engine SQLAlchemy (exigido pelo pandas moderno).
- **`create_tables()` idempotente:** manter `CREATE TABLE IF NOT EXISTS` (válido no Postgres) + a migração das PKs.

DDL alvo (resumo):
```sql
CREATE TABLE IF NOT EXISTS registros_defeitos (
    id bigserial PRIMARY KEY,
    "DATA DE PRODUÇÃO ACABAMENTO" text,
    "ORDEM MESTRE" text,
    ...
);
-- historico_cobrancas, pagamentos_concluidos: idem, com id bigserial PK
-- UserGal: username text PRIMARY KEY (já tem PK), demais colunas iguais
```

## 4. Camada de conexão (nova `database.py`)

```python
import streamlit as st
from sqlalchemy import create_engine

@st.cache_resource
def get_engine():
    # DATABASE_URL: pooler de transação do Supabase (porta 6543)
    # postgresql+psycopg2://postgres.<ref>:<senha>@aws-...-pooler.supabase.com:6543/postgres
    return create_engine(st.secrets["DATABASE_URL"], pool_pre_ping=True)

@contextmanager
def get_connection():
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()
```
- Usar o **Transaction Pooler (6543)** — Streamlit Cloud abre muitas conexões curtas; o pooler evita esgotar o limite do Postgres.
- `read_sql`/`to_sql` recebem a engine ou a connection SQLAlchemy.
- Escritas cruas: `conn.execute(text("... :p"), {"p": v})` + `conn.commit()`.

## 5. Secrets (`.streamlit/secrets.toml` / Streamlit Cloud)

```toml
DATABASE_URL = "postgresql+psycopg2://postgres.<ref>:<SENHA>@aws-0-<region>.pooler.supabase.com:6543/postgres"
# Remover GITHUB_TOKEN / GITHUB_REPO (não mais usados)
```
> A "chave token" (anon/service_role) **não** é usada neste caminho. Guardar só se um dia adotarem `supabase-py`/RLS.

## 6. Script de migração de dados (one-time)

`scripts/migrate_sqlite_to_supabase.py`:
1. Ler cada tabela do `dataset/analise_gal.db` com pandas (`read_sql`).
2. `create_tables()` no Postgres (com as PKs novas).
3. `df.to_sql(tabela, engine, if_exists="append", index=False)` para as 4 tabelas.
4. Validar contagens: linhas SQLite == linhas Postgres por tabela.
5. Conferir 1 usuário admin e login funcionando antes de cortar.

## 7. Ordem de execução

**Fase 0 — Preparação (sem tocar em prod)**
- Criar projeto Supabase, pegar `DATABASE_URL` (pooler).
- Adicionar `sqlalchemy`, `psycopg2-binary` ao `requirements.txt`.

**Fase 1 — Camada de conexão**
- Reescrever `src/data/database.py` (engine + `create_tables` Postgres com PKs).
- Adicionar `DATABASE_URL` em `settings.py`/secrets.

**Fase 2 — Adaptar os módulos de dados** (um a um, com teste após cada)
- `loader.py`, `cobranca_history.py`, `payment_history.py`, `auth/auth_db.py`: `?`→placeholder, `COLLATE NOCASE`→`LOWER()`, remover chamadas a `push_db_to_github`.
- `records_editor.py`: `rowid`→`id` (SELECT inclui `id`; UPDATE/`search` por `id`).

**Fase 3 — Remover o sync GitHub**
- Deletar `github_sync.py` e todos os imports/chamadas `push_db_to_github`.
- Remover `PyGithub` do `requirements.txt`.

**Fase 4 — Migrar os dados**
- Script pronto: `scripts/migrate_sqlite_to_supabase.py` (lê `dataset/analise_gal.db`, cria o
  schema no Postgres, migra as 4 tabelas, valida contagens e confere admin).
  Idempotente por padrão — roda de novo sem duplicar; `--force` ignora essa proteção.
  Testado localmente (schema + dados + hash/salt de usuário preservados); a execução
  final contra o Supabase real precisa ser feita por você, com a `DATABASE_URL`
  verdadeira em `.streamlit/secrets.toml` (este ambiente não tem acesso de rede ao
  Supabase). Rodar: `python scripts/migrate_sqlite_to_supabase.py`.

**Fase 5 — Validação ponta a ponta**
- Login/criar conta/esqueci a senha.
- Upload de planilha → append + dedupe.
- Lançar cobrança → marcar "Pago" (move p/ pagamentos_concluidos).
- Editar registro (rename em massa + edição por linha).
- Downloads xlsx (histórico e pagamentos).
- Teste de concorrência: duas abas escrevendo ao mesmo tempo.

**Fase 6 — Corte (cutover)**
- Configurar `DATABASE_URL` no Streamlit Cloud, remover secrets do GitHub.
- Manter `analise_gal.db` no repo como backup congelado por 1–2 semanas.
- (Opcional) tirar o `.db` do versionamento depois de estável.

## 8. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| `rowid`→`id` quebrar edição por linha | Migrar dados **antes** de trocar o código; testar `update_record_fields` |
| Esgotar conexões no Cloud | Usar pooler 6543 + `@st.cache_resource` na engine |
| Diferença de dialeto (datas como texto `dd/mm/yyyy`) | Mantidas como `text` — comportamento idêntico ao SQLite; sem conversão de tipo |
| Perda de dados no corte | Backup do `.db` congelado + validação de contagens |
| Segurança | Repo pode voltar a público depois (hashes saem do Git); senha do banco só nos secrets |

## 9. Fora de escopo (fases futuras opcionais)

- Supabase Auth (GoTrue) substituindo a auth própria.
- Row Level Security (RLS) — exigiria o cliente `supabase-py` (a "chave token").
- Realtime / normalização de datas para `date` nativo.
