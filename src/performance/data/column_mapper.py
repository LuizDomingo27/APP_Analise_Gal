# -*- coding: utf-8 -*-
"""
Descoberta das colunas da base.

A base do Gal tem cabeçalhos fixos (`src/config/settings.py::COLS`), então em
condições normais este módulo apenas os reconhece. Ele existe porque decide algo
que um de/para fixo não decidiria: QUAL coluna carrega a quantidade perdida.

Na base do Gal `REMONTE` é o TIPO do defeito ("PONTO ESTOURADO", "SEM ARREMATE")
e `QUANTIDADE` é o número de peças. Em outras planilhas do mesmo processo
`REMONTE` vem numérica e é ela a quantidade. A escolha é feita medindo os dados
(`numeric_ratio`), não o nome — ver `map()`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

import pandas as pd

from src.performance.domain.exceptions import DataValidationError
from src.performance.domain.models import ColumnMap


def normalize_label(value: object) -> str:
    """Cabeçalho sem acento, sem símbolo e em caixa alta, para comparação."""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


ALIASES: dict[str, tuple[str, ...]] = {
    "production_date": (
        "DATA DE PRODUCAO ACABAMENTO", "DATA DE PRODUCAO", "DATA PRODUCAO", "DATA",
    ),
    "master_order": ("ORDEM MESTRE", "ORDEM MASTER", "OM", "ORDEM"),
    "supplier": ("FORNECEDOR", "PARCEIRO", "OFICINA", "FACCAO"),
    "real_cut": ("REAL CORTADO", "TOTAL REAL CORTADO", "TOTAL DA ORDEM", "TOTAL ORDEM"),
    "quantity": ("QUANTIDADE", "QTD", "QTDE", "PECAS COM DEFEITO", "TOTAL DEFEITOS"),
    "remonte": ("REMONTE", "REMONTES", "TOTAL REMONTE", "PECAS REMONTE"),
    "minutes": ("MINUTOS GERADOS", "TOTAL DE MINUTOS", "MINUTOS", "MINUTOS GERADO"),
    "defect_type": ("TIPO DE DEFEITO", "DEFEITO", "CAUSA", "OCORRENCIA"),
    "material": ("MATERIAL", "REFERENCIA", "PRODUTO", "SKU"),
    "cost": ("VALOR DO PROCESSO BRL", "VALOR DO PROCESSO", "VALOR BRL", "CUSTO"),
}


def _find_column(columns: Iterable[object], aliases: Iterable[str]) -> str | None:
    normalized = {normalize_label(column): str(column) for column in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    for normalized_name, original in normalized.items():
        if any(alias in normalized_name or normalized_name in alias for alias in aliases):
            return original
    return None


def numeric_ratio(series: pd.Series) -> float:
    """Fração de valores da coluna que são lidos como número."""
    if series.empty:
        return 0.0
    if pd.api.types.is_numeric_dtype(series):
        return float(series.notna().mean())
    converted = pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False), errors="coerce"
    )
    return float(converted.notna().mean())


class ColumnMapper:
    """Mapeia os cabeçalhos da base para os campos da análise."""

    def map(self, frame: pd.DataFrame) -> ColumnMap:
        production_date = _find_column(frame.columns, ALIASES["production_date"])
        master_order = _find_column(frame.columns, ALIASES["master_order"])
        supplier = _find_column(frame.columns, ALIASES["supplier"])
        real_cut = _find_column(frame.columns, ALIASES["real_cut"])
        remonte = _find_column(frame.columns, ALIASES["remonte"])
        quantity = _find_column(frame.columns, ALIASES["quantity"])

        missing = [
            label
            for label, value in {
                "data de produção": production_date,
                "ordem mestre": master_order,
                "fornecedor": supplier,
                "real cortado": real_cut,
            }.items()
            if value is None
        ]
        if missing:
            raise DataValidationError(
                "Não foi possível localizar: " + ", ".join(missing) + ". "
                "Revise os cabeçalhos da base."
            )

        # A quantidade perdida sai da coluna que REALMENTE contém números. Na base
        # do Gal isso elege QUANTIDADE e rebaixa REMONTE a tipo de defeito — que é
        # exatamente o papel que ela tem lá.
        defect_quantity: str | None = None
        defect_type = _find_column(frame.columns, ALIASES["defect_type"])
        if remonte and numeric_ratio(frame[remonte]) >= 0.80:
            defect_quantity = remonte
        elif quantity and numeric_ratio(frame[quantity]) >= 0.80:
            defect_quantity = quantity
            if remonte:
                defect_type = remonte

        if defect_quantity is None:
            raise DataValidationError(
                "As colunas REMONTE/QUANTIDADE não contêm valores numéricos "
                "suficientes para calcular as perdas."
            )

        return ColumnMap(
            production_date=production_date,
            master_order=master_order,
            supplier=supplier,
            defect_quantity=defect_quantity,
            real_cut=real_cut,
            minutes=_find_column(frame.columns, ALIASES["minutes"]),
            defect_type=defect_type,
            material=_find_column(frame.columns, ALIASES["material"]),
            cost=_find_column(frame.columns, ALIASES["cost"]),
        )
