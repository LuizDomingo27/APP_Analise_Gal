# -*- coding: utf-8 -*-
"""Contratos de dados da análise de performance."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ColumnMap:
    """De/para entre os cabeçalhos da base e os campos da análise."""

    production_date: str
    master_order: str
    supplier: str
    defect_quantity: str
    real_cut: str
    minutes: str | None = None
    defect_type: str | None = None
    material: str | None = None
    cost: str | None = None


@dataclass
class DataQualityReport:
    """Diagnóstico da leitura — alimenta a aba "Qualidade dos dados"."""

    source_name: str
    sheet_name: str
    source_rows: int
    valid_rows: int = 0
    order_rows: int = 0
    discarded_rows: int = 0
    invalid_dates: int = 0
    invalid_numbers: int = 0
    missing_real_cut: int = 0
    future_dates: int = 0
    excessive_loss_orders: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalysisDataset:
    """Par (linhas validadas, ordens consolidadas) + como se chegou nele.

    `rows`   → uma linha por ocorrência de defeito (grão da base).
    `orders` → uma linha por (fornecedor, ordem mestre), com o REAL CORTADO
               contado uma única vez. É sobre `orders` que performance e índice
               de defeitos são calculados; somar `rows` inflaria o real cortado.
    """

    rows: pd.DataFrame
    orders: pd.DataFrame
    column_map: ColumnMap
    quality: DataQualityReport


@dataclass(frozen=True)
class DashboardMetrics:
    """KPIs do topo da página, já no recorte dos filtros."""

    suppliers: int
    suppliers_below_target: int
    orders: int
    real_cut: float
    defect_pieces: float
    approved_pieces: float
    minutes_generated: float
    defect_cost: float
    performance: float
    defect_rate: float
    worst_supplier: str
    worst_supplier_rate: float
    best_supplier: str
    best_supplier_rate: float
