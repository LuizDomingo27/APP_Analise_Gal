"""
Testes dos design tokens (src/config/theme.py).

Estes testes não checam estética — checam as três fronteiras onde uma variável
CSS silenciosamente NÃO funciona. Todas as três foram encontradas durante o
refactor que introduziu os tokens, e nenhuma falha de forma visível: a cor
simplesmente some, sem erro no console e sem teste vermelho. Daí a guarda.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.config.theme import (
    ACCENT_TOKENS,
    CLEAN,
    DEFAULT_THEME,
    accent_alpha,
    accent_color,
    get_theme,
    theme_css_vars,
    theme_style_tag,
)

ROOT = Path(__file__).resolve().parents[1]

# Arquivos cujo CSS vai para o documento principal (st.markdown) -> var() resolve.
APP_FILES = [
    "app.py",
    "src/ui/cobranca.py",
    "src/ui/layout.py",
    "src/ui/login.py",
    "src/ui/user_manager.py",
    "src/ui/backup.py",
    "src/ui/records_editor.py",
    "src/ui/defeitos_imagens.py",
    "src/auth/session.py",
    "src/ui/metrics.py",
    "src/ui/historico_defeitos.py",
    "src/ui/filters.py",
    "src/data/cobranca_history.py",
]

# Geram documento standalone fora do app — HTML de impressão (<!DOCTYPE) e
# planilha xlsx. Nenhum deles enxerga o nosso :root: cor ali é hex literal.
EXPORT_FILES = ["src/ui/preview.py", "src/services/backup_exporter.py"]

# Paletas em Python entregues ao ECharts, que não lê CSS.
NON_CSS_FILES = ["src/config/settings.py", "src/charts/builder.py"]

VAR_RE = re.compile(r"var\(--ag-([a-z0-9-]+)\)")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _call_name(node: ast.Call) -> str:
    f, parts = node.func, []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def _iframe_calls(src: str) -> list[ast.Call]:
    return [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and _call_name(n).endswith("components.html")
    ]


# ── O módulo em si ────────────────────────────────────────────────────────────

def test_tema_padrao_existe():
    assert get_theme(DEFAULT_THEME) is CLEAN


@pytest.mark.parametrize("nome", [None, "", "inexistente", "DARK", "clean "])
def test_tema_desconhecido_cai_no_clean_sem_levantar(nome):
    """Cor nunca pode derrubar a página: valor velho em sessão/banco vira clean."""
    assert get_theme(nome) is CLEAN


def test_todo_token_tem_valor_css_valido():
    hexa = re.compile(r"^#[0-9A-F]{6}$")
    canais = re.compile(r"^\d{1,3},\d{1,3},\d{1,3}$")
    for nome, valor in CLEAN.items():
        if nome.endswith("-rgb"):
            assert canais.match(valor), f"{nome}={valor!r} deveria ser 'R,G,B'"
            assert all(0 <= int(c) <= 255 for c in valor.split(",")), f"{nome} fora de 0-255"
        else:
            assert hexa.match(valor), f"{nome}={valor!r} deveria ser #RRGGBB maiúsculo"


def test_css_vars_declara_todos_os_tokens_com_prefixo():
    css = theme_css_vars()
    assert css.startswith(":root{") and css.endswith("}")
    for nome in CLEAN:
        assert f"--ag-{nome}:" in css
    # o prefixo existe para não sobrescrever variáveis do próprio Streamlit
    assert "--text-color:" not in css
    assert "--primary-color:" not in css


def test_style_tag_embrulha_as_vars():
    assert theme_style_tag() == f"<style>{theme_css_vars()}</style>"


# ── Fronteira 1: tokens usados precisam existir ───────────────────────────────

@pytest.mark.parametrize("rel", APP_FILES)
def test_todo_var_usado_esta_definido(rel):
    """Um var(--ag-typo) não gera erro: a cor só some. Este teste é o erro."""
    usados = set(VAR_RE.findall(_read(rel)))
    faltando = sorted(usados - set(CLEAN))
    assert not faltando, f"{rel} usa tokens inexistentes: {faltando}"


def test_app_declara_os_tokens_antes_do_css():
    """Sem o :root injetado, TODO var(--ag-*) da página fica sem valor."""
    src = _read("app.py")
    assert "theme_style_tag()" in src
    assert src.index("theme_style_tag()") < src.index("<style>"), \
        "o :root precisa ser injetado antes do primeiro bloco de CSS"


# ── Fronteira 2: iframe é outro documento ─────────────────────────────────────

@pytest.mark.parametrize("rel", APP_FILES)
def test_iframe_que_usa_token_embute_o_proprio_root(rel):
    """components.html roda em iframe: o :root da página NÃO atravessa.

    Sem embutir theme_css_vars() no <style> do iframe, todo var(--ag-*) lá dentro
    fica sem valor e o componente perde as cores — sem nenhum erro visível.
    """
    src = _read(rel)
    for call in _iframe_calls(src):
        trecho = ast.get_source_segment(src, call) or ""
        if "var(--ag-" not in trecho:
            continue
        assert "theme_css_vars()" in trecho, (
            f"{rel}: components.html na linha {call.lineno} usa var(--ag-*) mas não "
            f"embute theme_css_vars() — as cores não vão resolver dentro do iframe"
        )


# ── Fronteira 3: exportação não enxerga o :root ───────────────────────────────

@pytest.mark.parametrize("rel", EXPORT_FILES + NON_CSS_FILES)
def test_arquivos_fora_de_alcance_nao_usam_tokens(rel):
    """HTML de exportação e paletas do ECharts precisam de cor literal.

    O <!DOCTYPE> de export vira PDF/impressão (documento próprio, sem o nosso
    :root) e o ECharts recebe cor por Python, não por CSS. var(--ag-*) nesses
    lugares não resolve para cor nenhuma.
    """
    achados = sorted(set(VAR_RE.findall(_read(rel))))
    assert not achados, (
        f"{rel} usa var(--ag-*) fora do alcance do :root: {achados}. "
        f"Use hex literal aqui."
    )


# ── Acentos: cor sólida + versões translúcidas coerentes ─────────────────────

def test_todo_acento_tem_par_rgb_com_os_canais_certos():
    """`--ag-danger` e `--ag-danger-rgb` têm de ser a MESMA cor.

    accent_color e accent_alpha entregam as duas formas do mesmo acento; se os
    canais divergirem do hex, a borda sólida e a translúcida do card ficam com
    cores diferentes — e nada acusa.
    """
    for token in sorted(ACCENT_TOKENS):
        assert token in CLEAN, f"acento {token!r} não tem cor sólida"
        rgb = CLEAN.get(f"{token}-rgb")
        assert rgb, f"acento {token!r} não tem par --ag-{token}-rgb"
        hexa = CLEAN[token].lstrip("#")
        esperado = ",".join(str(int(hexa[i:i + 2], 16)) for i in (0, 2, 4))
        assert rgb == esperado, (
            f"--ag-{token}={CLEAN[token]} mas --ag-{token}-rgb={rgb} "
            f"(deveria ser {esperado})"
        )


def test_todo_par_rgb_bate_com_a_cor_de_mesmo_nome():
    """Vale para qualquer token, não só acentos: -rgb nunca pode mentir."""
    for nome, valor in CLEAN.items():
        if not nome.endswith("-rgb"):
            continue
        base = nome[:-4]
        if base not in CLEAN:
            continue  # canal sem cor sólida correspondente (ex.: shadow, white)
        hexa = CLEAN[base].lstrip("#")
        esperado = ",".join(str(int(hexa[i:i + 2], 16)) for i in (0, 2, 4))
        assert valor == esperado, f"--ag-{nome}={valor} não corresponde a {CLEAN[base]}"


@pytest.mark.parametrize("token", sorted(ACCENT_TOKENS))
def test_accent_color_e_alpha_produzem_css_valido(token):
    assert accent_color(token) == f"var(--ag-{token})"
    assert accent_alpha(token, 0.5) == f"rgba(var(--ag-{token}-rgb),0.5)"


@pytest.mark.parametrize("ruim", ["bg-app", "text-primary", "inexistente", "", "DANGER"])
def test_acento_invalido_levanta_em_vez_de_gerar_css_quebrado(ruim):
    """Sem par -rgb, accent_alpha geraria `rgba(var(--ag-bg-app-rgb),...)`, que
    não resolve. Melhor estourar no teste do que sumir a cor em produção."""
    with pytest.raises(ValueError):
        accent_color(ruim)
    with pytest.raises(ValueError):
        accent_alpha(ruim, 0.5)


def test_ninguem_concatena_sufixo_de_alpha_em_cor():
    """`{accent}52` montava um hex de 8 dígitos concatenando texto.

    Era o único padrão do app incompatível com var() — `var(--ag-info)52` não é
    cor nenhuma e a borda sumia sem erro. Foi substituído por accent_alpha(),
    que deriva o alpha pelos canais. Este teste impede a volta do padrão.
    """
    suffix = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}[0-9A-Fa-f]{2}\b")
    for rel in APP_FILES:
        src = _read(rel)
        for i, linha in enumerate(src.splitlines(), 1):
            if linha.lstrip().startswith("#"):
                continue  # comentário que explica o padrão, não o usa
            m = suffix.search(linha)
            if m and not re.search(r"\}(px|em|rem|deg)", m.group(0)):
                pytest.fail(
                    f"{rel}:{i} concatena sufixo de alpha em cor ({m.group(0)!r}); "
                    f"use accent_alpha() — concatenação não funciona com var()"
                )


def test_mini_kpi_recebe_nome_de_token_e_nao_cor():
    """O acento do card é o NOME de um token; cor literal ali volta a fixar o
    valor fora do tema."""
    src = _read("src/ui/cobranca.py")
    tree = ast.parse(src)

    # AST e não regex: `_mini_kpi(c4, "...", d.strftime("%d/%m/%Y"), "info")` tem
    # parênteses aninhados, e um `_mini_kpi\([^)]*\)` casa só até o primeiro ')' —
    # parando ANTES do argumento de acento, justamente o que se quer checar.
    chamadas = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _call_name(n) == "_mini_kpi"
    ]
    assert chamadas, "esperava encontrar chamadas de _mini_kpi"

    for call in chamadas:
        acento = call.args[3] if len(call.args) > 3 else None
        if isinstance(acento, ast.Constant):
            assert acento.value in ACCENT_TOKENS, (
                f"src/ui/cobranca.py:{call.lineno}: _mini_kpi recebeu "
                f"{acento.value!r}, que não é um acento válido {sorted(ACCENT_TOKENS)}"
            )

    # O acento também chega por variável (dias_accent), vinda desta função:
    for n in ast.walk(tree):
        if not (isinstance(n, ast.FunctionDef) and n.name == "_dias_para_vencer_label"):
            continue
        for ret in [x for x in ast.walk(n) if isinstance(x, ast.Return)]:
            for elt in getattr(ret.value, "elts", []):
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    if elt.value in ACCENT_TOKENS:
                        continue
                    assert not elt.value.startswith(("#", "var(")), (
                        f"src/ui/cobranca.py:{ret.lineno}: _dias_para_vencer_label "
                        f"devolve {elt.value!r}; o _mini_kpi espera nome de acento"
                    )


# ── CSS não deve pegar cor da paleta do ECharts ──────────────────────────────

@pytest.mark.parametrize("rel", APP_FILES)
def test_css_nao_interpola_settings_colors(rel):
    """`{COLORS['text_muted']}` fazia o CSS depender da paleta do ECharts.

    A cor até saía certa, mas vinha de um dict Python: não trocaria com o tema.
    Eram 75 pontos. O CSS tem de pedir o token.
    """
    achados = re.findall(r"\{COLORS\[['\"][a-z_]+['\"]\]\}", _read(rel))
    assert not achados, (
        f"{rel} pega cor de settings.COLORS dentro de CSS ({len(achados)}x): "
        f"{sorted(set(achados))}. Use var(--ag-*)."
    )
