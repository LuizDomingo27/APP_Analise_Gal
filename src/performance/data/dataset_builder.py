# -*- coding: utf-8 -*-
"""
Construção do dataset de performance a partir do DataFrame da base.

Fronteira deliberada: este módulo NÃO fala com o banco. Ele recebe o DataFrame
que `src.data.historico_defeitos.load_historico()` já leu (e já cacheou) e o
converte no par (linhas validadas, ordens consolidadas). Assim a página de
Performance não abre uma segunda consulta ao Postgres — ver a nota sobre a fonte
e a carga em `pages/7_Performance.py`.

A conversão é pura e determinística, o que permite à página envolvê-la em
`st.cache_data` e não recalcular a agregação a cada movimento de filtro.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.performance.config import BASES, DEFAULT_BASE
from src.performance.data.column_mapper import ColumnMapper
from src.performance.domain.calculations import aggregate_orders
from src.performance.domain.exceptions import DataValidationError
from src.performance.domain.models import AnalysisDataset, ColumnMap, DataQualityReport


def parse_number(series: pd.Series) -> pd.Series:
    """Converte números que podem vir com separador brasileiro, R$ ou %."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    def convert(value: object) -> float:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return np.nan
        text = str(value).strip().replace("R$", "").replace("%", "").replace(" ", "")
        if not text:
            return np.nan
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except (TypeError, ValueError):
            return np.nan

    return series.map(convert)


#: Colunas que a análise realmente lê — 8 das 13 da base.
ANALYSIS_KEYS = ("date", "order", "supplier", "quantity", "defect",
                 "real_cut", "minutes", "value_brl")


def base_fingerprint(df: pd.DataFrame) -> str:
    """Assinatura do CONTEÚDO da base, para usar como chave de cache.

    Existe para não deixar o `st.cache_data` hashear/pickle o DataFrame inteiro a
    cada rerun, mas sem abrir mão de correção. Um resumo por contagem e somas
    seria mais barato e estaria ERRADO: `src/data/records_editor.py` existe
    justamente para corrigir digitação em FORNECEDOR e REMONTE, e renomear um
    fornecedor não muda contagem, data máxima nem soma nenhuma — a análise
    continuaria agrupando pelos nomes antigos enquanto o resto do app já
    mostraria a correção.

    `hash_pandas_object` é O(n) vetorizado em C sobre as 8 colunas que a análise
    lê, e muda com qualquer célula alterada.
    """
    from src.config.settings import COLS

    columns = [COLS[key] for key in ANALYSIS_KEYS if COLS[key] in df.columns]
    digest = int(pd.util.hash_pandas_object(df[columns], index=False).sum())
    return f"{len(df)}:{digest}"


def build_dataset(
    frame: pd.DataFrame,
    source_name: str = BASES[DEFAULT_BASE].source_name,
    table_name: str = BASES[DEFAULT_BASE].table,
) -> AnalysisDataset:
    """Valida, normaliza e consolida o DataFrame da base em ordens mestre."""
    if frame is None or frame.empty:
        raise DataValidationError("A base está vazia — não há o que analisar.")

    column_map = ColumnMapper().map(frame)
    report = DataQualityReport(
        source_name=source_name, sheet_name=table_name, source_rows=len(frame)
    )
    rows = _normalize(frame, column_map, report)
    orders = aggregate_orders(rows, report)
    report.valid_rows = len(rows)
    report.order_rows = len(orders)
    return AnalysisDataset(rows=rows, orders=orders, column_map=column_map, quality=report)


def _normalize(frame: pd.DataFrame, mapping: ColumnMap, report: DataQualityReport) -> pd.DataFrame:
    rows = pd.DataFrame(index=frame.index)
    rows["production_date"] = pd.to_datetime(
        frame[mapping.production_date], errors="coerce", dayfirst=True
    )
    rows["master_order"] = (
        frame[mapping.master_order].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    )
    rows["supplier"] = (
        frame[mapping.supplier].astype("string")
        .str.replace(" ", " ", regex=False)  # espaco nao separavel do Excel
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    rows["defect_pieces"] = parse_number(frame[mapping.defect_quantity])
    rows["real_cut"] = parse_number(frame[mapping.real_cut])
    rows["minutes_generated"] = (
        parse_number(frame[mapping.minutes]).fillna(0) if mapping.minutes else 0.0
    )
    rows["defect_cost"] = (
        parse_number(frame[mapping.cost]).fillna(0) if mapping.cost else 0.0
    )
    rows["defect_type"] = (
        frame[mapping.defect_type].astype("string").fillna("Não informado").str.strip()
        if mapping.defect_type
        else "Não informado"
    )
    rows["material"] = (
        frame[mapping.material].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
        if mapping.material
        else ""
    )

    report.invalid_dates = int(rows["production_date"].isna().sum())
    report.invalid_numbers = int(rows[["defect_pieces", "real_cut"]].isna().any(axis=1).sum())
    report.missing_real_cut = int(rows["real_cut"].isna().sum())

    # `real_cut > 0` é requisito, não preferência: ele é o DENOMINADOR do índice
    # de defeitos. Linha sem real cortado não tem performance definida, e mantê-la
    # com zero produziria divisão por zero mascarada de 0%.
    valid = (
        rows["production_date"].notna()
        & rows["master_order"].notna()
        & rows["supplier"].notna()
        & rows["defect_pieces"].notna()
        & rows["real_cut"].notna()
        & rows["supplier"].ne("")
        & rows["master_order"].ne("")
        & rows["real_cut"].gt(0)
        & rows["defect_pieces"].ge(0)
    )
    report.discarded_rows = int((~valid).sum())
    rows = rows.loc[valid].copy()
    if rows.empty:
        raise DataValidationError(
            "Nenhuma linha da base passou na validação: confira REAL CORTADO, "
            "datas de produção e fornecedores."
        )

    iso = rows["production_date"].dt.isocalendar()
    rows["week"] = iso["year"].astype(str) + "-S" + iso["week"].astype(str).str.zfill(2)
    rows["month"] = rows["production_date"].dt.strftime("%Y-%m")

    today = pd.Timestamp(date.today())
    report.future_dates = int(rows["production_date"].gt(today).sum())
    if report.discarded_rows:
        report.warnings.append(
            f"{report.discarded_rows} linha(s) da base foram desconsideradas na análise."
        )
    if report.future_dates:
        report.warnings.append(f"{report.future_dates} registro(s) possuem data futura.")
    if mapping.defect_type and mapping.defect_quantity != mapping.defect_type:
        report.warnings.append(
            f"A quantidade de perdas foi lida de '{mapping.defect_quantity}'; "
            f"'{mapping.defect_type}' foi tratada como tipo de defeito."
        )
    return rows.reset_index(drop=True)
