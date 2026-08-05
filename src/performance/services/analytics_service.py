# -*- coding: utf-8 -*-
"""
Métricas, rankings e recortes da análise de performance.

Tudo aqui opera em memória sobre o dataset já construído: mover um filtro não
volta ao Postgres. É o que permite os sliders de meta e de corte de perda serem
interativos sem custo de banco.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from src.performance.domain.calculations import aggregate_orders
from src.performance.domain.models import AnalysisDataset, DashboardMetrics

SUMMARY_COLUMNS = [
    "supplier", "orders", "real_cut", "defect_pieces", "approved_pieces",
    "minutes_generated", "defect_cost", "defect_rate", "performance", "status",
]


class AnalyticsService:
    @staticmethod
    def filter_dataset(
        dataset: AnalysisDataset,
        suppliers: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        weeks: list[str] | None = None,
        months: list[str] | None = None,
    ) -> AnalysisDataset:
        """Recorta as LINHAS e reconsolida as ordens a partir do recorte.

        Reagregar (em vez de filtrar `orders` direto) é intencional: se um filtro
        de data corta parte de uma OM, a ordem precisa ser recontada apenas com o
        que sobrou, senão o real cortado do período viria inteiro.
        """
        rows = dataset.rows

        mask = pd.Series(True, index=rows.index)
        if suppliers:
            mask &= rows["supplier"].isin(suppliers)
        if start_date:
            mask &= rows["production_date"].dt.date >= start_date
        if end_date:
            mask &= rows["production_date"].dt.date <= end_date
        if weeks:
            mask &= rows["week"].isin(weeks)
        if months:
            mask &= rows["month"].isin(months)
        rows = rows.loc[mask].copy()

        return AnalysisDataset(
            rows=rows.reset_index(drop=True),
            orders=aggregate_orders(rows).reset_index(drop=True),
            column_map=dataset.column_map,
            quality=replace(dataset.quality),
        )

    @staticmethod
    def supplier_summary(orders: pd.DataFrame, target: float = 0.90) -> pd.DataFrame:
        """Uma linha por fornecedor, ordenada da pior para a melhor performance."""
        if orders.empty:
            return pd.DataFrame(columns=SUMMARY_COLUMNS)

        summary = orders.groupby("supplier", as_index=False).agg(
            orders=("master_order", "nunique"),
            real_cut=("real_cut", "sum"),
            defect_pieces=("defect_pieces", "sum"),
            minutes_generated=("minutes_generated", "sum"),
            defect_cost=("defect_cost", "sum"),
        )
        summary["approved_pieces"] = summary["real_cut"] - summary["defect_pieces"]
        summary["defect_rate"] = summary["defect_pieces"].div(summary["real_cut"]).fillna(0)
        summary["performance"] = 1 - summary["defect_rate"]
        summary["status"] = np.where(
            summary["performance"] < target, "Abaixo da meta", "Dentro da meta"
        )
        return (
            summary[SUMMARY_COLUMNS]
            .sort_values(["performance", "real_cut"], ascending=[True, False])
            .reset_index(drop=True)
        )

    @staticmethod
    def metrics(orders: pd.DataFrame, target: float = 0.90) -> DashboardMetrics:
        summary = AnalyticsService.supplier_summary(orders, target)
        if orders.empty or summary.empty:
            return DashboardMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "—", 0, "—", 0)

        real_cut = float(orders["real_cut"].sum())
        defect_pieces = float(orders["defect_pieces"].sum())
        performance = (real_cut - defect_pieces) / real_cut if real_cut else 0.0
        worst = summary.iloc[0]
        best = summary.iloc[-1]
        return DashboardMetrics(
            suppliers=int(summary["supplier"].nunique()),
            suppliers_below_target=int(summary["performance"].lt(target).sum()),
            orders=int(orders["master_order"].nunique()),
            real_cut=real_cut,
            defect_pieces=defect_pieces,
            approved_pieces=real_cut - defect_pieces,
            minutes_generated=float(orders["minutes_generated"].sum()),
            defect_cost=float(orders["defect_cost"].sum()),
            performance=performance,
            defect_rate=1 - performance,
            worst_supplier=str(worst["supplier"]),
            worst_supplier_rate=float(worst["defect_rate"]),
            best_supplier=str(best["supplier"]),
            best_supplier_rate=float(best["defect_rate"]),
        )

    @staticmethod
    def critical_orders(orders: pd.DataFrame, loss_threshold: float) -> pd.DataFrame:
        """Ordens cuja perda alcança o corte escolhido, das piores para as melhores."""
        if orders.empty:
            return orders.copy()
        return (
            orders.loc[orders["defect_rate"].ge(loss_threshold)]
            .sort_values(["defect_rate", "defect_pieces"], ascending=False)
            .reset_index(drop=True)
        )

    @staticmethod
    def performance_trend(orders: pd.DataFrame, frequency: str = "month") -> pd.DataFrame:
        if orders.empty:
            return pd.DataFrame(columns=["period", "performance", "defect_rate", "real_cut"])
        period_column = "week" if frequency == "week" else "month"
        trend = orders.groupby(period_column, as_index=False).agg(
            real_cut=("real_cut", "sum"), defect_pieces=("defect_pieces", "sum")
        )
        trend["performance"] = 1 - trend["defect_pieces"].div(trend["real_cut"]).fillna(0)
        trend["defect_rate"] = 1 - trend["performance"]
        return trend.rename(columns={period_column: "period"}).sort_values("period")

    @staticmethod
    def defect_breakdown(rows: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
        """Peças perdidas por tipo de defeito — calculado sobre LINHAS, não ordens.

        O tipo do defeito vive na ocorrência; nas ordens ele já virou uma lista
        concatenada. Por isso este recorte é o único que parte de `rows`.
        """
        if rows.empty:
            return pd.DataFrame(columns=["defect_type", "defect_pieces", "share"])
        result = rows.groupby("defect_type", as_index=False).agg(
            defect_pieces=("defect_pieces", "sum")
        )
        total = float(result["defect_pieces"].sum())
        result["share"] = result["defect_pieces"] / total if total else 0
        return (
            result.sort_values("defect_pieces", ascending=False)
            .head(limit)
            .reset_index(drop=True)
        )
