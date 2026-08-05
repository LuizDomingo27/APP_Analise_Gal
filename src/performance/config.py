# -*- coding: utf-8 -*-
"""
Constantes e paleta da análise de performance.

A paleta aqui é entregue ao ECharts, que não lê CSS — mesma razão pela qual
`src/config/settings.py` e `src/charts/builder.py` também seguem com hex em
Python (ver a nota em `src/config/theme.py`). Os valores foram alinhados aos
tokens `--ag-*` do tema "clean" para que os gráficos desta página tenham a mesma
cor dos do dashboard principal.

O CSS desta página, esse sim, consome `var(--ag-*)` — ver `presentation/theme.py`.
"""

from dataclasses import dataclass

#: Meta de performance padrão do slider (90%).
DEFAULT_TARGET = 0.90

#: Corte padrão de perda por ordem para a aba de ordens críticas (10%).
DEFAULT_LOSS_THRESHOLD = 0.10

# ── Bases analisáveis ─────────────────────────────────────────────────────────
# O app tem duas tabelas de defeitos com schema IDÊNTICO e significados
# diferentes. A escolha entre elas muda o que a análise quer dizer, então ela é
# explícita na tela em vez de fixa no código.


@dataclass(frozen=True)
class BaseOption:
    """Uma origem de dados oferecida no seletor da página."""

    key: str
    label: str
    table: str
    source_name: str
    caption: str
    #: Preenchido quando a base tem uma armadilha de interpretação.
    warning: str | None = None


BASES: dict[str, BaseOption] = {
    "completa": BaseOption(
        key="completa",
        label="Completa",
        table="historico_defeitos",
        source_name="Histórico permanente de defeitos",
        caption=(
            "Todo o histórico importado. Nenhum registro sai desta base, "
            "então a performance é comparável entre períodos."
        ),
    ),
    "atual": BaseOption(
        key="atual",
        label="Atual",
        table="registros_defeitos",
        source_name="Base ativa de defeitos",
        caption="Somente os defeitos que ainda não foram cobrados.",
        warning=(
            "A base **Atual** perde os registros de cada fornecedor no momento "
            "em que a cobrança é emitida. Ela mostra o que está **em aberto** — "
            "não serve para comparar performance entre períodos, porque os "
            "piores fornecedores saem dela justamente ao serem cobrados. "
            "Para avaliar o parceiro, use a base **Completa**."
        ),
    ),
}

#: A base histórica é o padrão: é a única em que "performance no período"
#: significa o que o nome diz.
DEFAULT_BASE = "completa"

# ── Paleta (espelha os tokens --ag-* do tema clean) ───────────────────────────
COLORS = {
    "background":  "#FAFCFB",  # --ag-bg-app
    "surface":     "#FFFFFF",  # --ag-bg-surface
    "surface_alt": "#F2F7F5",  # --ag-bg-surface-alt
    "border":      "#E8EFEC",  # --ag-border-hairline
    "cyan":        "#00B884",  # --ag-primary
    "cyan_dark":   "#00805C",  # --ag-primary-dark
    "lime":        "#3DDC97",  # verde secundário da COLOR_SEQUENCE do app
    "amber":       "#EF9F27",  # --ag-warning
    "danger":      "#E24B4A",  # --ag-danger
    "info":        "#0EA5C7",  # --ag-info
    "text":        "#0D1B17",  # --ag-text-primary
    "muted":       "#4A5752",  # --ag-text-muted
}
