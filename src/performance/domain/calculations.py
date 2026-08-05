# -*- coding: utf-8 -*-
"""Consolidação por Ordem Mestre — o núcleo da análise de performance."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.performance.domain.models import DataQualityReport

ORDER_COLUMNS = [
    "supplier", "master_order", "production_start", "production_end", "production_date",
    "production_period", "defect_pieces", "real_cut", "minutes_generated", "defect_cost",
    "defect_types", "materials", "occurrence_rows", "defect_rate", "performance",
    "approved_pieces", "week", "month",
]


def aggregate_orders(rows: pd.DataFrame, report: DataQualityReport | None = None) -> pd.DataFrame:
    """Consolida cada OM uma única vez por fornecedor, mesmo cruzando datas.

    A regra que justifica o módulo inteiro está no `real_cut=("real_cut", "max")`:
    o REAL CORTADO é um atributo da ORDEM, e a base o repete em cada linha de
    defeito daquela ordem. Somá-lo multiplicaria o total pelo número de defeitos
    registrados e o índice de defeitos cairia artificialmente. `max` (e não
    `first`) porque a mesma OM pode aparecer com o valor preenchido em umas
    linhas e zerado em outras.

    Já `defect_pieces`, `minutes_generated` e `defect_cost` são atributos da
    OCORRÊNCIA — esses somam.
    """
    if rows.empty:
        return pd.DataFrame(columns=ORDER_COLUMNS)

    def join_unique(values: pd.Series) -> str:
        clean = [str(value) for value in values.dropna().unique() if str(value).strip()]
        return ", ".join(clean[:6]) + ("…" if len(clean) > 6 else "")

    orders = (
        rows.groupby(["supplier", "master_order"], as_index=False, dropna=False)
        .agg(
            production_start=("production_date", "min"),
            production_end=("production_date", "max"),
            defect_pieces=("defect_pieces", "sum"),
            real_cut=("real_cut", "max"),
            minutes_generated=("minutes_generated", "sum"),
            defect_cost=("defect_cost", "sum"),
            defect_types=("defect_type", join_unique),
            materials=("material", join_unique),
            occurrence_rows=("defect_pieces", "size"),
        )
        .sort_values("production_end", ascending=False)
    )
    orders["production_date"] = orders["production_end"]
    start_text = orders["production_start"].dt.strftime("%d/%m/%Y")
    end_text = orders["production_end"].dt.strftime("%d/%m/%Y")
    orders["production_period"] = np.where(
        start_text.eq(end_text), end_text, start_text + " a " + end_text
    )
    orders["defect_rate"] = (
        orders["defect_pieces"].div(orders["real_cut"])
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
    )
    orders["performance"] = 1.0 - orders["defect_rate"]
    orders["approved_pieces"] = orders["real_cut"] - orders["defect_pieces"]
    iso = orders["production_date"].dt.isocalendar()
    orders["week"] = iso["year"].astype(str) + "-S" + iso["week"].astype(str).str.zfill(2)
    orders["month"] = orders["production_date"].dt.strftime("%Y-%m")

    excessive = int(orders["defect_rate"].gt(1).sum())
    if report is not None:
        report.excessive_loss_orders = excessive
        if excessive:
            report.warnings.append(
                f"{excessive} ordem(ns) têm perdas acima de 100% e devem ser revisadas na origem."
            )
    return orders[ORDER_COLUMNS].reset_index(drop=True)
