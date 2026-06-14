"""
Data processing layer.
All business logic, aggregations, and KPI computations live here.
No UI or chart code — pure data transformation.
"""

import pandas as pd
from src.config.settings import COLS


class DataProcessor:
    """Encapsulates all analytical computations over a (filtered) DataFrame."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df

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
        """Average remonte rate across all records, as a percentage."""
        return float(self.df[COLS["pct_remonte"]].mean() * 100)

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _agg_sum(self, group_cols: list[str], value_col: str) -> pd.DataFrame:
        return (
            self.df.groupby(group_cols)[value_col]
            .sum()
            .reset_index()
        )
