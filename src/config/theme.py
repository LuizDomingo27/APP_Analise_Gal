"""
Tokens de cor do app (design tokens).

Por que este módulo existe
──────────────────────────
Até aqui cada cor era um hex escrito à mão dentro do CSS de cada página (~400
literais em 12 arquivos). Trocar o visual — ou oferecer um segundo tema —
significava caçar e reescrever todos. Aqui cada cor ganha um NOME que descreve o
seu PAPEL ("fundo da página", "texto secundário", "borda no hover"), e o CSS
passa a pedir o papel via `var(--ag-*)`. Trocar de tema vira trocar este
dicionário.

O prefixo `--ag-`
─────────────────
Todo token é prefixado para não colidir com as variáveis que o próprio Streamlit
declara no `:root` (ex.: `--primary-color`, `--text-color`). Sem prefixo, um
token nosso chamado `--text-color` sobrescreveria silenciosamente o do framework
e mudaria widgets que nunca tocamos.

Onde estes tokens NÃO alcançam
──────────────────────────────
Variável CSS vive no documento onde foi declarada. Existem três fronteiras no
app, e só a primeira é coberta por `theme_style_tag()` no app.py:

  1. Documento principal (st.markdown)  → alcança. É o uso normal.
  2. Iframe (components.html)           → NÃO alcança: é outro documento. Cada
                                          iframe precisa embutir o próprio
                                          `:root` — use `theme_css_vars()` na
                                          `<style>` dele.
  3. HTML de exportação (<!DOCTYPE ...) → NÃO alcança, e de propósito: relatório
                                          impresso/PDF é branco em qualquer tema.
                                          Esses arquivos (src/ui/preview.py,
                                          src/services/exporter.py) seguem com
                                          hex fixo — não tokenize.

Fora de escopo também: src/config/settings.py e src/charts/builder.py. São
paletas em Python entregues ao ECharts, que não lê CSS.
"""

from __future__ import annotations

# ── Tema "clean" ──────────────────────────────────────────────────────────────
# Os valores são exatamente os que já estavam no CSS: este dicionário não muda
# um pixel, só dá nome ao que existia. Cada entrada é (token -> valor CSS).
CLEAN: dict[str, str] = {
    # ── Superfícies ──────────────────────────────────────────────────────────
    "bg-app":         "#FAFCFB",  # fundo da página
    "bg-surface":     "#FFFFFF",  # cards, inputs, header, tabelas
    "bg-surface-alt": "#F2F7F5",  # zebra de tabela, cabeçalho de grid, upload
    # Tooltip é escuro POR DESIGN, inclusive no tema clean — não é "o fundo
    # invertido". Mantê-lo como token próprio impede que um tema dark o
    # clareie junto com bg-surface e deixe texto claro sobre fundo claro.
    "bg-inverse":     "#061210",

    # ── Texto ────────────────────────────────────────────────────────────────
    "text-primary":  "#0D1B17",
    "text-muted":    "#4A5752",
    "text-subtle":   "#7C8985",
    "text-nav":      "#6B7A74",  # link inativo da navbar
    "text-disabled": "#9AA7A2",
    "text-on-accent": "#04231B",  # texto sobre fundo verde forte
    "text-on-dark":   "#FFFFFF",  # texto sobre botão/gradiente escuro ou saturado

    # ── Marca ────────────────────────────────────────────────────────────────
    "primary":        "#00B884",
    "primary-dark":   "#00805C",
    "primary-bright": "#00E5A0",
    "primary-light":  "#5FF6C6",
    "primary-neon":   "#00FF9C",
    "primary-grad-from": "#00C994",
    "primary-grad-to":   "#00A578",

    # ── Bordas ───────────────────────────────────────────────────────────────
    # Mesmo valor de text-primary hoje, papel diferente: é a borda que o input e
    # o botão assumem no hover/focus. Separado justamente para que um tema dark
    # possa clarear o texto sem que toda borda de foco vá junto.
    "border-strong":   "#0D1B17",
    "border-hairline": "#E8EFEC",

    # ── Semânticas ───────────────────────────────────────────────────────────
    "danger":  "#E24B4A",
    # Segundo vermelho, quase igual ao danger (#E24B4A vs #E74C3C). É uma
    # inconsistência herdada, não um papel: unificar mudaria pixels, então fica
    # como token à parte para ser resolvido depois, fora deste refactor.
    "danger-alt": "#E74C3C",
    "warning": "#EF9F27",
    "info":    "#0EA5C7",

    # ── Acentos pontuais (significado de dado, não de tema) ───────────────────
    "accent-purple": "#534AB7",  # código de lançamento
    "accent-blue":   "#0F86A3",  # valor da empresa (contraparte do fornecedor)
    "accent-coral":  "#D85A30",  # vencido

    # ── Canais RGB ───────────────────────────────────────────────────────────
    # Para os ~200 rgba() com alpha variável. `rgba(var(--ag-primary-rgb), .18)`
    # mantém o alpha no ponto de uso e ainda deixa a cor trocar com o tema — o
    # que um token de cor pronta não permitiria (seriam ~40 tokens de alpha).
    "primary-rgb":        "0,184,132",
    "primary-dark-rgb":   "0,128,92",
    "primary-bright-rgb": "0,229,160",
    "primary-neon-rgb":   "0,255,156",
    "text-primary-rgb":   "13,27,23",
    "text-subtle-rgb":    "124,137,133",
    "danger-rgb":         "226,75,74",
    "danger-dark-rgb":    "194,57,43",
    "warning-rgb":        "239,159,39",
    "info-rgb":           "14,165,199",
    "accent-coral-rgb":   "216,90,48",
    "white-rgb":          "255,255,255",
    "shadow-rgb":         "0,0,0",
}

# Tokens que existem nas duas formas: cor pronta (`--ag-danger`) e canais
# (`--ag-danger-rgb`). Só estes servem de "acento" para componentes que precisam
# derivar versões translúcidas da mesma cor — ver accent_color/accent_alpha.
ACCENT_TOKENS = frozenset({
    "primary", "primary-dark", "primary-bright",
    "danger", "warning", "info", "text-subtle", "accent-coral",
})


def accent_color(token: str) -> str:
    """Cor sólida do acento: `accent_color("danger")` -> `var(--ag-danger)`."""
    if token not in ACCENT_TOKENS:
        raise ValueError(
            f"acento desconhecido: {token!r}. Use um de {sorted(ACCENT_TOKENS)} — "
            f"precisa ter par -rgb para as versões translúcidas."
        )
    return f"var(--ag-{token})"


def accent_alpha(token: str, alpha: float) -> str:
    """Versão translúcida do acento, derivada pelos canais RGB.

    Existe para substituir a concatenação de sufixo hex (`{accent}52`), que
    montava um hex de 8 dígitos e por isso era incompatível com var(): o token
    não é texto de cor, e `var(--ag-info)52` não resolve para cor nenhuma — a
    borda sumia sem erro nenhum. Aqui o alpha entra por canal, não por
    concatenação, então funciona com qualquer tema.
    """
    if token not in ACCENT_TOKENS:
        raise ValueError(f"acento desconhecido: {token!r}")
    return f"rgba(var(--ag-{token}-rgb),{alpha})"

THEMES: dict[str, dict[str, str]] = {
    "clean": CLEAN,
}

DEFAULT_THEME = "clean"


def get_theme(name: str | None = None) -> dict[str, str]:
    """Retorna o dicionário de tokens do tema. Nome desconhecido cai no padrão.

    Não levanta: um tema inválido (valor velho em sessão/banco, typo) deve
    degradar para o clean, nunca derrubar a página inteira por causa de cor.
    """
    return THEMES.get(name or DEFAULT_THEME, CLEAN)


def theme_css_vars(name: str | None = None) -> str:
    """Bloco `:root{...}` com os tokens do tema — SEM a tag <style>.

    Use dentro do `<style>` de um `components.html`, que é um documento próprio e
    não enxerga o `:root` da página. Para o documento principal use
    `theme_style_tag()`.
    """
    tokens = get_theme(name)
    decls = "".join(f"--ag-{k}:{v};" for k, v in tokens.items())
    return f":root{{{decls}}}"


def theme_style_tag(name: str | None = None) -> str:
    """`<style>` completo com os tokens — para injetar no documento principal."""
    return f"<style>{theme_css_vars(name)}</style>"
