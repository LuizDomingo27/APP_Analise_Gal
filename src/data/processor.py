"""
Data processing layer.
All business logic, aggregations, and KPI computations live here.
No UI or chart code — pure data transformation.
"""

import pandas as pd
from src.config.settings import COLS

#: Nomes dos meses em pt-BR. Fixos no código de propósito: `strftime("%B")`
#: depende do locale do processo, que no Streamlit Cloud é o padrão em inglês.
MONTH_NAMES_PT = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)


class DataProcessor:
    """Encapsulates all analytical computations over a (filtered) DataFrame."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        #: Memo do recorte mensal (ver `_month_series`). O processador é tratado
        #: como imutável em todo o app: é criado a partir do DataFrame já
        #: filtrado e descartado ao fim do render.
        self._months_cache: pd.Series | None = None

    # ── KPIs ─────────────────────────────────────────────────────────────────

    def total_defects(self) -> int:
        return int(self.df[COLS["quantity"]].sum())

    def total_cost(self) -> float:
        return float(self.df[COLS["value_brl"]].sum())

    def total_minutes(self) -> float:
        return float(self.df[COLS["minutes"]].sum())

    def unique_suppliers(self) -> int:
        return int(self.df[COLS["supplier"]].nunique())

    def unique_orders(self) -> int:
        return int(self.df[COLS["order"]].nunique())

    def avg_remonte_rate_pct(self) -> float:
        """Average remonte rate across all records, as a percentage.
        Returns 0.0 (not NaN) when there are no records to average."""
        if self.df.empty:
            return 0.0
        mean = self.df[COLS["pct_remonte"]].mean()
        return float(mean * 100) if pd.notna(mean) else 0.0

    # ── Defect type ──────────────────────────────────────────────────────────

    def by_defect_type(self) -> pd.DataFrame:
        return self._agg_sum([COLS["defect"]], COLS["quantity"]).sort_values(
            COLS["quantity"], ascending=False
        )

    # ── Location ─────────────────────────────────────────────────────────────

    def by_location(self) -> pd.DataFrame:
        return self._agg_sum([COLS["location"]], COLS["quantity"]).sort_values(
            COLS["quantity"], ascending=False
        )

    # ── Supplier ─────────────────────────────────────────────────────────────

    def by_supplier_quantity(self, top: int = 10) -> pd.DataFrame:
        return self._agg_sum([COLS["supplier"]], COLS["quantity"]).sort_values(
            COLS["quantity"], ascending=False
        ).head(top)

    def by_supplier_cost(self, top: int = 10) -> pd.DataFrame:
        return self._agg_sum([COLS["supplier"]], COLS["value_brl"]).sort_values(
            COLS["value_brl"], ascending=False
        ).head(top)

    def by_supplier_rate(self, top: int = 10) -> pd.DataFrame:
        result = (
            self.df.groupby(COLS["supplier"])[COLS["pct_remonte"]]
            .mean()
            .mul(100)
            .reset_index()
            .sort_values(COLS["pct_remonte"], ascending=False)
            .head(top)
        )
        return result

    # ── Key combination (location × defect) ──────────────────────────────────

    def by_key(self, top: int = 12) -> pd.DataFrame:
        return (
            self._agg_sum([COLS["location"], COLS["defect"]], COLS["quantity"])
            .sort_values(COLS["quantity"], ascending=False)
            .head(top)
        )

    # ── Temporal ─────────────────────────────────────────────────────────────

    def by_date(self) -> pd.DataFrame:
        return self._agg_sum([COLS["date"]], COLS["quantity"]).sort_values(COLS["date"])

    def by_date_cost(self) -> pd.DataFrame:
        return self._agg_sum([COLS["date"]], COLS["value_brl"]).sort_values(COLS["date"])

    # ── Mês vigente e comparativo mensal ─────────────────────────────────────
    # "Mês vigente" é o mês da data mais RECENTE do recorte já filtrado — e não
    # o mês do calendário de hoje. Assim o gráfico por dia e o card comparativo
    # continuam mostrando algo útil quando o usuário filtra um período passado
    # (com o mês do calendário, a tela ficaria vazia sempre que o filtro não
    # alcançasse o mês corrente).

    def _month_series(self) -> pd.Series:
        """Período mensal (period[M]) de cada linha; NaT onde a data é inválida.

        Memoizado: uma única tela chama os métodos de mês meia dúzia de vezes
        (dois gráficos + o card comparativo), e reconverter a coluna de datas a
        cada chamada seria varrer a base inteira várias vezes por render.
        """
        if self._months_cache is None:
            if self.df.empty or COLS["date"] not in self.df.columns:
                self._months_cache = pd.Series(index=self.df.index, dtype="period[M]")
            else:
                self._months_cache = (
                    pd.to_datetime(self.df[COLS["date"]], errors="coerce")
                    .dt.to_period("M")
                )
        return self._months_cache

    def current_month(self) -> pd.Period | None:
        """Mês mais recente presente no recorte, ou None se não houver datas."""
        months = self._month_series().dropna()
        if months.empty:
            return None
        return months.max()

    @staticmethod
    def month_label(period: "pd.Period | None") -> str:
        """Rótulo pt-BR de um período mensal (ex.: 'Agosto/2026')."""
        if period is None:
            return "—"
        return f"{MONTH_NAMES_PT[period.month - 1]}/{period.year}"

    def rows_in_month(self, period: "pd.Period | None") -> pd.DataFrame:
        """Subconjunto do recorte pertencente ao mês informado (vazio se None)."""
        if period is None:
            return self.df.iloc[0:0]
        return self.df[self._month_series() == period]

    def by_date_current_month(self) -> pd.DataFrame:
        """`by_date` restrito ao mês vigente do recorte."""
        return DataProcessor(self.rows_in_month(self.current_month())).by_date()

    def by_date_cost_current_month(self) -> pd.DataFrame:
        """`by_date_cost` restrito ao mês vigente do recorte."""
        return DataProcessor(self.rows_in_month(self.current_month())).by_date_cost()

    def month_over_month(self) -> dict:
        """Compara o mês vigente com o mês CALENDÁRIO imediatamente anterior.

        Chaves do dicionário retornado:
            has_current / has_previous → bool
            current_label / previous_label → str ("Agosto/2026")
            current_pieces / previous_pieces / pieces_delta → int
            current_value / previous_value / value_delta → float
            pieces_pct / value_pct → float | None (None quando a base é zero)

        Mês anterior sem registros no recorte → has_previous False, totais 0 e
        percentuais None: o card exibe "sem base de comparação" em vez de uma
        variação de 100% que não significa nada.
        """
        curr = self.current_month()
        prev = curr - 1 if curr is not None else None

        months = self._month_series()
        cur_rows  = self.df[months == curr] if curr is not None else self.df.iloc[0:0]
        prev_rows = self.df[months == prev] if prev is not None else self.df.iloc[0:0]

        cur_pieces,  cur_value  = self._pieces_and_value(cur_rows)
        prev_pieces, prev_value = self._pieces_and_value(prev_rows)

        return {
            "has_current":    curr is not None and not cur_rows.empty,
            "has_previous":   prev is not None and not prev_rows.empty,
            "current_label":  self.month_label(curr),
            "previous_label": self.month_label(prev),
            "current_pieces":  cur_pieces,
            "previous_pieces": prev_pieces,
            "pieces_delta":    cur_pieces - prev_pieces,
            "pieces_pct":      self._pct_change(cur_pieces, prev_pieces),
            "current_value":   cur_value,
            "previous_value":  prev_value,
            "value_delta":     round(cur_value - prev_value, 2),
            "value_pct":       self._pct_change(cur_value, prev_value),
        }

    @staticmethod
    def _pieces_and_value(df: pd.DataFrame) -> tuple[int, float]:
        """Soma quantidade e valor de um recorte, tolerando colunas ausentes."""
        def _sum(col: str) -> float:
            if col not in df.columns:
                return 0.0
            total = pd.to_numeric(df[col], errors="coerce").sum()
            return float(total) if pd.notna(total) else 0.0

        return int(_sum(COLS["quantity"])), round(_sum(COLS["value_brl"]), 2)

    @staticmethod
    def _pct_change(current: float, previous: float) -> float | None:
        """Variação percentual; None quando não há base anterior (evita ÷ 0)."""
        if not previous:
            return None
        return (current - previous) / previous * 100

    # ── Cross matrix ─────────────────────────────────────────────────────────

    def supplier_defect_matrix(self) -> pd.DataFrame:
        return self._agg_sum([COLS["supplier"], COLS["defect"]], COLS["quantity"])

    # ── Top problematic orders ────────────────────────────────────────────────

    def top_orders(self, top: int = 10) -> pd.DataFrame:
        return self._agg_sum([COLS["order"]], COLS["quantity"]).sort_values(
            COLS["quantity"], ascending=False
        ).head(top)

    # ── Auto-insights ─────────────────────────────────────────────────────────

    def top_supplier_by_quantity(self) -> tuple[str, int]:
        row = self.by_supplier_quantity(1)
        if row.empty:
            return "N/A", 0
        return row.iloc[0][COLS["supplier"]], int(row.iloc[0][COLS["quantity"]])

    def top_supplier_by_cost(self) -> tuple[str, float]:
        row = self.by_supplier_cost(1)
        if row.empty:
            return "N/A", 0.0
        return row.iloc[0][COLS["supplier"]], float(row.iloc[0][COLS["value_brl"]])

    def top_defect(self) -> tuple[str, int, float]:
        row = self.by_defect_type()
        if row.empty:
            return "N/A", 0, 0.0
        name = row.iloc[0][COLS["defect"]]
        qty  = int(row.iloc[0][COLS["quantity"]])
        pct  = qty / self.total_defects() * 100 if self.total_defects() else 0.0
        return name, qty, pct

    # ── Weekly variation ─────────────────────────────────────────────────────

    def weekly_remonte_by_supplier(self, top: int = 10) -> pd.DataFrame:
        """Tabela 1: variação semanal do total de remonte por fornecedor.

        Compara as duas últimas semanas ISO com dados e retorna a variação
        na quantidade total de remonte por fornecedor.
        """
        df = self.df.copy()
        df["_week"] = df[COLS["date"]].dt.isocalendar().week.astype(int)
        weeks_sorted = sorted(df["_week"].unique())
        if len(weeks_sorted) < 2:
            return pd.DataFrame(columns=[
                "Fornecedor", "Sem. Anterior (Qtd)", "Sem. Atual (Qtd)", "Variação (Qtd)"
            ])
        prev_w, curr_w = weeks_sorted[-2], weeks_sorted[-1]
        grp = (
            df.groupby(["_week", COLS["supplier"]])[COLS["quantity"]]
            .sum()
            .reset_index()
        )
        prev = grp[grp["_week"] == prev_w].rename(
            columns={COLS["quantity"]: "Sem. Anterior (Qtd)"}
        )
        curr = grp[grp["_week"] == curr_w].rename(
            columns={COLS["quantity"]: "Sem. Atual (Qtd)"}
        )
        merged = prev.merge(curr, on=COLS["supplier"], how="outer", suffixes=("", "_"))
        merged["Sem. Anterior (Qtd)"] = merged["Sem. Anterior (Qtd)"].fillna(0).astype(int)
        merged["Sem. Atual (Qtd)"] = merged["Sem. Atual (Qtd)"].fillna(0).astype(int)
        merged["Variação (Qtd)"] = (
            merged["Sem. Atual (Qtd)"] - merged["Sem. Anterior (Qtd)"]
        )
        result = (
            merged[[COLS["supplier"], "Sem. Anterior (Qtd)", "Sem. Atual (Qtd)", "Variação (Qtd)"]]
            .rename(columns={COLS["supplier"]: "Fornecedor"})
            .sort_values("Variação (Qtd)", ascending=False)
            .head(top)
            .reset_index(drop=True)
        )
        return result

    def weekly_remonte_variation(self) -> pd.DataFrame:
        """Tabela 2: variação semanal geral da quantidade total de remonte.

        Mostra cada semana ISO, o total de remontes, e a variação em % em relação à anterior.
        """
        df = self.df.copy()
        df["_week"] = df[COLS["date"]].dt.isocalendar().week.astype(int)
        grp = (
            df.groupby("_week")[COLS["quantity"]]
            .sum()
            .reset_index()
            .sort_values("_week")
        )
        grp["Período"] = grp["_week"].apply(lambda w: f"W-{w}")
        grp["Total Remontes"] = grp[COLS["quantity"]].astype(int)
        grp["Variação (%)"] = grp["Total Remontes"].pct_change().mul(100).round(2)
        return (
            grp[["Período", "Total Remontes", "Variação (%)"]]
            .reset_index(drop=True)
        )


    def weekly_cost_variation(self) -> pd.DataFrame:
        """Tabela 3: variação semanal do custo de remonte (R$).

        Mostra cada semana ISO e a variação absoluta e percentual em relação
        à semana anterior.
        """
        df = self.df.copy()
        df["_week"] = df[COLS["date"]].dt.isocalendar().week.astype(int)
        grp = (
            df.groupby("_week")[COLS["value_brl"]]
            .sum()
            .reset_index()
            .sort_values("_week")
        )
        grp["Período"] = grp["_week"].apply(lambda w: f"W-{w}")
        grp["Valor Total (R$)"] = grp[COLS["value_brl"]].round(2)
        grp["Variação (R$)"] = grp["Valor Total (R$)"].diff().round(2)
        grp["Variação (%)"] = (
            grp["Valor Total (R$)"].pct_change().mul(100).round(2)
        )
        return (
            grp[["Período", "Valor Total (R$)", "Variação (R$)", "Variação (%)"]]
            .reset_index(drop=True)
        )

    # ── Resumo por fornecedor (para o filtro por faixa) ───────────────────────

    #: Métricas do filtro por faixa → coluna agregada de `supplier_summary`.
    SUPPLIER_SUMMARY_METRICS = {
        "remonte": "total_remonte",
        "ordens":  "total_ordens",
        "valor":   "total_valor",
    }

    def supplier_summary(self) -> pd.DataFrame:
        """Agrega o histórico por fornecedor (uma linha por fornecedor).

        Colunas do DataFrame retornado, ordenado por valor total desc.:
            fornecedor       → str
            total_remonte    → int   (nº de registros/remontes do fornecedor)
            total_quantidade → int   (soma da quantidade — peças com defeito)
            total_ordens     → int   (ordens mestre — OM — únicas)
            total_valor      → float (soma do valor do processo, R$)

        DataFrame vazio na entrada → mesmas colunas, sem linhas.
        """
        cols = [
            "fornecedor", "total_remonte", "total_quantidade",
            "total_ordens", "total_valor",
        ]
        if self.df.empty:
            return pd.DataFrame(columns=cols)

        grp = self.df.groupby(COLS["supplier"])
        summary = (
            pd.DataFrame(
                {
                    "total_remonte":    grp.size(),
                    "total_quantidade": grp[COLS["quantity"]].sum(),
                    "total_ordens":     grp[COLS["order"]].nunique(),
                    "total_valor":      grp[COLS["value_brl"]].sum(),
                }
            )
            .reset_index()
            .rename(columns={COLS["supplier"]: "fornecedor"})
        )
        summary["total_remonte"]    = summary["total_remonte"].astype(int)
        summary["total_quantidade"] = summary["total_quantidade"].astype(int)
        summary["total_ordens"]     = summary["total_ordens"].astype(int)
        summary["total_valor"]      = summary["total_valor"].astype(float)
        return (
            summary[cols]
            .sort_values("total_valor", ascending=False)
            .reset_index(drop=True)
        )

    def supplier_summary_in_range(
        self, metric: str, low: float, high: float
    ) -> pd.DataFrame:
        """`supplier_summary` restrito aos fornecedores cuja `metric` cai em [low, high].

        `metric` ∈ SUPPLIER_SUMMARY_METRICS ("remonte" | "ordens" | "valor").
        Intervalo inclusivo nas duas pontas; se `low > high` os limites são
        invertidos automaticamente. Retorna as mesmas colunas de `supplier_summary`.
        """
        try:
            col = self.SUPPLIER_SUMMARY_METRICS[metric]
        except KeyError:
            raise ValueError(
                f"Métrica inválida: {metric!r}. "
                f"Use uma de {sorted(self.SUPPLIER_SUMMARY_METRICS)}."
            ) from None

        summary = self.supplier_summary()
        if summary.empty:
            return summary

        lo, hi = (low, high) if low <= high else (high, low)
        mask = (summary[col] >= lo) & (summary[col] <= hi)
        return summary[mask].reset_index(drop=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _agg_sum(self, group_cols: list[str], value_col: str) -> pd.DataFrame:
        return (
            self.df.groupby(group_cols)[value_col]
            .sum()
            .reset_index()
        )
