# -*- coding: utf-8 -*-
"""
Testes da camada do catálogo de imagens de defeitos
(src/data/defeitos_imagens.py): normalização da chave de busca, cadastro/upsert
de imagem (salvar_imagem), leitura do catálogo já com data URI
(carregar_catalogo), casamento defeito⇆imagem (imagem_do_defeito), listagem
(listar_defeitos) e exclusão (excluir_imagem).

Cobre também os caminhos de exceção (nome vazio, arquivo vazio, tabela ausente)
para garantir que a camada nunca deixe o app quebrar.

Segue o mesmo padrão de test_historico_defeitos.py: isola a camada num SQLite
temporário por teste. As correções de portabilidade (CURRENT_TIMESTAMP no lugar
de now(), upsert ON CONFLICT) valem tanto no SQLite quanto no Postgres.
"""

import base64
import io

import pytest
from sqlalchemy import text

import src.data.database as db
import src.data.defeitos_imagens as di


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Isola a camada de imagens num SQLite temporário para cada teste."""
    db_path = tmp_path / "test_defeitos_imagens.db"
    sqlite_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setattr(db, "_database_url", lambda: sqlite_url)
    db.get_engine.clear()
    db.create_tables.clear()
    di.carregar_catalogo.clear()
    di.listar_defeitos.clear()
    db.create_tables()
    yield db_path
    db.get_engine.clear()
    db.create_tables.clear()
    di.carregar_catalogo.clear()
    di.listar_defeitos.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

# 1x1 PNG transparente (bytes reais de imagem) para os testes.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class _FakeUpload:
    """Imita um UploadedFile do Streamlit: expõe .read() e .type."""

    def __init__(self, data: bytes, mime: str = "image/png"):
        self._buf = io.BytesIO(data)
        self.type = mime

    def read(self) -> bytes:
        return self._buf.read()


def _count() -> int:
    with db.get_connection() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM defeitos_imagens")).fetchone()[0]


# ── normalizar_defeito (a chave de busca) ─────────────────────────────────────

@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("imgRevelEsgarcando", "REVELESGARCANDO"),
        ("Revel Esgarçando", "REVELESGARCANDO"),
        ("REVEL ESGARÇANDO", "REVELESGARCANDO"),
        ("imgPontoEstourado", "PONTOESTOURADO"),
        ("PONTO ESTOURADO", "PONTOESTOURADO"),
        ("Ponto-Falho!", "PONTOFALHO"),
        ("  img Sem Arremate  ", "SEMARREMATE"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalizar_defeito(entrada, esperado):
    assert di.normalizar_defeito(entrada) == esperado


def test_normalizar_defeito_casa_grafias_diferentes():
    """O caso central do recurso: nome do arquivo e nome da planilha convergem."""
    assert di.normalizar_defeito("imgRevelEsgarcando") == di.normalizar_defeito("Revel Esgarçando")


# ── carregar_catalogo ─────────────────────────────────────────────────────────

def test_carregar_catalogo_vazio_retorna_dict_vazio(temp_db):
    assert di.carregar_catalogo() == {}


def test_carregar_catalogo_monta_data_uri(temp_db):
    di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Ponto Estourado")
    di.carregar_catalogo.clear()

    catalogo = di.carregar_catalogo()
    assert "PONTOESTOURADO" in catalogo
    item = catalogo["PONTOESTOURADO"]
    assert item["nome"] == "Ponto Estourado"
    # data URI = prefixo + base64 exato dos bytes gravados
    esperado_b64 = base64.b64encode(_PNG_BYTES).decode()
    assert item["data_uri"] == f"data:image/png;base64,{esperado_b64}"


def test_carregar_catalogo_autocura_com_tabela_ausente(temp_db):
    """
    Regressão: se a tabela não existir, carregar_catalogo deve recriá-la via
    _ensure_schema e retornar {} — sem vazar traceback para a UI.
    """
    with db.get_connection() as conn:
        conn.execute(text("DROP TABLE defeitos_imagens"))
        conn.commit()
    di.carregar_catalogo.clear()

    assert di.carregar_catalogo() == {}
    with db.get_connection() as conn:
        conn.execute(text("SELECT * FROM defeitos_imagens"))  # existe de novo


# ── salvar_imagem (cadastro / upsert) ─────────────────────────────────────────

def test_salvar_imagem_insere_novo(temp_db):
    chave = di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Ponto Estourado")
    assert chave == "PONTOESTOURADO"
    assert _count() == 1


def test_salvar_imagem_upsert_substitui_mesma_chave(temp_db):
    """Grafias diferentes → mesma chave → substitui (não duplica)."""
    di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Ponto Estourado")
    novos_bytes = _PNG_BYTES + b"\x00extra"
    di.salvar_imagem(_FakeUpload(novos_bytes), "imgPontoEstourado")

    assert _count() == 1  # não duplicou
    di.carregar_catalogo.clear()
    catalogo = di.carregar_catalogo()
    esperado_b64 = base64.b64encode(novos_bytes).decode()
    assert catalogo["PONTOESTOURADO"]["data_uri"].endswith(esperado_b64)
    # o rótulo também é atualizado para o último nome informado
    assert catalogo["PONTOESTOURADO"]["nome"] == "imgPontoEstourado"


def test_salvar_imagem_preserva_mime(temp_db):
    di.salvar_imagem(_FakeUpload(_PNG_BYTES, mime="image/jpeg"), "Troca")
    di.carregar_catalogo.clear()
    assert di.carregar_catalogo()["TROCA"]["data_uri"].startswith("data:image/jpeg;base64,")


def test_salvar_imagem_rejeita_nome_vazio(temp_db):
    with pytest.raises(ValueError):
        di.salvar_imagem(_FakeUpload(_PNG_BYTES), "   ")


def test_salvar_imagem_rejeita_nome_sem_chave_valida(temp_db):
    # Nome só com símbolos → chave normalizada vazia → ValueError.
    with pytest.raises(ValueError):
        di.salvar_imagem(_FakeUpload(_PNG_BYTES), "!!! ###")


def test_salvar_imagem_rejeita_arquivo_vazio(temp_db):
    with pytest.raises(ValueError):
        di.salvar_imagem(_FakeUpload(b""), "Ponto Falho")


# ── imagem_do_defeito (casamento na consulta) ─────────────────────────────────

def test_imagem_do_defeito_casa_por_chave_normalizada(temp_db):
    di.salvar_imagem(_FakeUpload(_PNG_BYTES), "imgRevelEsgarcando")
    di.carregar_catalogo.clear()
    catalogo = di.carregar_catalogo()

    # O defeito no registro vem "cru" (grafia da planilha) e ainda assim casa.
    assert di.imagem_do_defeito("Revel Esgarçando", catalogo) is not None
    assert di.imagem_do_defeito("REVEL ESGARÇANDO", catalogo) is not None


def test_imagem_do_defeito_none_quando_sem_cadastro(temp_db):
    catalogo = di.carregar_catalogo()
    assert di.imagem_do_defeito("Defeito Sem Imagem", catalogo) is None


# ── listar_defeitos ───────────────────────────────────────────────────────────

def test_listar_defeitos_vazio(temp_db):
    assert di.listar_defeitos() == []


def test_listar_defeitos_ordem_alfabetica(temp_db):
    di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Ponto Estourado")
    di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Esgarçando")
    di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Troca")

    nomes = [d["nome"] for d in di.listar_defeitos()]
    assert nomes == ["Esgarçando", "Ponto Estourado", "Troca"]


# ── excluir_imagem ────────────────────────────────────────────────────────────

def test_excluir_imagem_remove(temp_db):
    chave = di.salvar_imagem(_FakeUpload(_PNG_BYTES), "Ponto Estourado")
    assert di.excluir_imagem(chave) == 1
    assert _count() == 0


def test_excluir_imagem_inexistente_retorna_zero(temp_db):
    assert di.excluir_imagem("NAOEXISTE") == 0


def test_excluir_imagem_chave_vazia_retorna_zero(temp_db):
    assert di.excluir_imagem("") == 0
