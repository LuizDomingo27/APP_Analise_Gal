# -*- coding: utf-8 -*-
"""
Testes da análise de performance de fornecedores (página 7).

O foco é a regra que justifica o módulo: consolidar a Ordem Mestre sem
duplicar o REAL CORTADO. É o ponto onde um erro não aparece como exceção —
aparece como número plausível e errado.
"""

import pandas as pd
import pytest

from src.config.settings import COLS
from src.performance.config import BASES, DEFAULT_BASE
from src.performance.data.column_mapper import ColumnMapper, normalize_label
from src.performance.data.dataset_builder import base_fingerprint, build_dataset
from src.performance.domain.calculations import aggregate_orders
from src.performance.domain.exceptions import DataValidationError
from src.performance.services.analytics_service import AnalyticsService
from src.performance.services.report_service import PdfReportService, SupplierExportService


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_frame() -> pd.DataFrame:
    """Base no formato exato do Postgres do Gal (mesmas colunas de COLS).

    A OM 1001 tem DUAS linhas de defeito com o mesmo REAL CORTADO de 1000 — é o
    caso que distingue consolidar de somar.
    """
    return pd.DataFrame({
        COLS["date"]: pd.to_datetime(
            ["2026-06-01", "2026-06-02", "2026-06-02", "2026-06-03"]
        ),
        COLS["order"]: [1001, 1001, 1002, 1003],
        COLS["material"]: [10, 10, 11, 12],
        COLS["supplier"]: ["OFICINA A", "OFICINA A", "OFICINA A", "OFICINA B"],
        COLS["quantity"]: [40, 60, 10, 2],
        COLS["location"]: ["CÓS", "BARRA", "CÓS", "BOLSO"],
        COLS["defect"]: ["PONTO ESTOURADO", "SEM ARREMATE", "PONTO ESTOURADO", "TROCAR"],
        COLS["real_cut"]: [1000, 1000, 500, 100],
        COLS["pct_remonte"]: [0.04, 0.06, 0.02, 0.02],
        COLS["key"]: ["a", "b", "c", "d"],
        COLS["process_time"]: [0.5, 0.4, 0.3, 0.2],
        COLS["minutes"]: [20.0, 24.0, 3.0, 0.4],
        COLS["value_brl"]: [50.0, 70.0, 12.0, 3.5],
    })


# ── A regra central: real cortado conta uma vez por ordem ─────────────────────

def test_real_cut_counted_once_per_order():
    rows = pd.DataFrame({
        "supplier": ["A", "A"],
        "master_order": ["10", "10"],
        "production_date": pd.to_datetime(["2026-06-01", "2026-06-02"]),
        "defect_pieces": [40, 60],
        "real_cut": [1000, 1000],
        "minutes_generated": [2.0, 3.0],
        "defect_cost": [10.0, 15.0],
        "defect_type": ["Costura", "Mancha"],
        "material": ["1", "1"],
    })
    order = aggregate_orders(rows).iloc[0]

    assert order["real_cut"] == 1000          # não 2000
    assert order["defect_pieces"] == 100      # ocorrências somam
    assert order["defect_cost"] == 25.0       # custo é da ocorrência, soma
    assert order["performance"] == pytest.approx(0.90)
    assert order["production_period"] == "01/06/2026 a 02/06/2026"


def test_same_order_for_different_suppliers_stays_separate():
    """OM repetida entre fornecedores é ordem diferente — não pode fundir."""
    rows = pd.DataFrame({
        "supplier": ["A", "B"],
        "master_order": ["10", "10"],
        "production_date": pd.to_datetime(["2026-06-01", "2026-06-01"]),
        "defect_pieces": [10, 20],
        "real_cut": [100, 200],
        "minutes_generated": [1.0, 2.0],
        "defect_cost": [5.0, 8.0],
        "defect_type": ["X", "Y"],
        "material": ["1", "2"],
    })
    orders = aggregate_orders(rows)

    assert len(orders) == 2
    assert orders["real_cut"].sum() == 300


def test_empty_rows_return_typed_empty_frame():
    orders = aggregate_orders(pd.DataFrame())
    assert orders.empty
    assert "defect_cost" in orders.columns


# ── Descoberta de colunas ─────────────────────────────────────────────────────

def test_normalize_label_removes_accents_and_symbols():
    assert normalize_label(" Data de Produção / Acabamento ") == "DATA DE PRODUCAO ACABAMENTO"


def test_textual_remonte_becomes_defect_type_and_quantity_carries_loss(base_frame):
    """Na base do Gal REMONTE é texto: a perda tem de sair de QUANTIDADE."""
    mapping = ColumnMapper().map(base_frame)

    assert mapping.defect_quantity == COLS["quantity"]
    assert mapping.defect_type == COLS["defect"]
    assert mapping.cost == COLS["value_brl"]


def test_numeric_remonte_has_priority():
    frame = pd.DataFrame({
        "DATA": ["01/06/2026"], "OM": [1], "FORNECEDOR": ["A"],
        "REMONTE": [12], "REAL CORTADO": [100], "QUANTIDADE": [999],
    })
    assert ColumnMapper().map(frame).defect_quantity == "REMONTE"


def test_missing_required_columns_is_user_facing():
    with pytest.raises(DataValidationError, match="Não foi possível localizar"):
        ColumnMapper().map(pd.DataFrame({"FORNECEDOR": ["A"]}))


# ── Construção do dataset a partir da base ────────────────────────────────────

def test_build_dataset_consolidates_gal_base(base_frame):
    dataset = build_dataset(base_frame)

    assert len(dataset.rows) == 4      # quatro ocorrências
    assert len(dataset.orders) == 3    # três ordens mestre

    om_1001 = dataset.orders.loc[dataset.orders["master_order"] == "1001"].iloc[0]
    assert om_1001["real_cut"] == 1000
    assert om_1001["defect_pieces"] == 100
    assert om_1001["defect_cost"] == 120.0


def test_rows_without_real_cut_are_discarded_and_reported(base_frame):
    """Sem real cortado não há denominador — a linha sai e o descarte é contado."""
    frame = base_frame.copy()
    frame.loc[0, COLS["real_cut"]] = 0

    dataset = build_dataset(frame)

    assert dataset.quality.discarded_rows == 1
    assert len(dataset.rows) == 3
    assert any("desconsideradas" in warning for warning in dataset.quality.warnings)


def test_empty_base_raises_user_facing_error():
    with pytest.raises(DataValidationError, match="vazia"):
        build_dataset(pd.DataFrame())


# ── Seleção de base ───────────────────────────────────────────────────────────
# As duas tabelas têm schema idêntico, então trocá-las não quebra nada — só muda
# o significado do resultado. Estes testes travam o mapeamento.

def test_bases_map_to_the_right_tables():
    assert BASES["completa"].table == "historico_defeitos"
    assert BASES["atual"].table == "registros_defeitos"


def test_default_base_is_the_permanent_history():
    """O padrão precisa ser a base que NÃO perde registros ao cobrar."""
    assert DEFAULT_BASE in BASES
    assert BASES[DEFAULT_BASE].table == "historico_defeitos"


def test_only_the_active_base_carries_a_warning():
    """A base Atual encolhe a cada cobrança — isso tem de estar avisado na tela."""
    assert BASES["atual"].warning
    assert "cobrança" in BASES["atual"].warning
    assert BASES["completa"].warning is None


def test_dataset_records_which_base_produced_it(base_frame):
    """O diagnóstico carimba a origem — é o que distingue as duas telas."""
    for key, option in BASES.items():
        dataset = build_dataset(
            base_frame, source_name=option.source_name, table_name=option.table
        )
        assert dataset.quality.sheet_name == option.table
        assert dataset.quality.source_name == option.source_name


# ── Impressão digital / invalidação de cache ──────────────────────────────────
# A página cacheia a consolidação usando `base_fingerprint` como chave. Se a
# assinatura não mudar quando a base muda, a Performance mostra dados velhos
# enquanto o resto do app já mostra os novos. Os casos abaixo são exatamente as
# edições que as outras páginas permitem.

def test_fingerprint_is_stable_for_identical_data(base_frame):
    assert base_fingerprint(base_frame) == base_fingerprint(base_frame.copy())


def test_fingerprint_detects_supplier_rename(base_frame):
    """`records_editor` existe para unificar nomes de fornecedor com typo.

    Uma renomeação não muda contagem de linhas, data máxima nem soma alguma —
    é o caso que um fingerprint por totais deixaria passar.
    """
    renamed = base_frame.copy()
    renamed.loc[0, COLS["supplier"]] = "OFICINA A LTDA."

    assert len(renamed) == len(base_frame)
    assert renamed[COLS["quantity"]].sum() == base_frame[COLS["quantity"]].sum()
    assert renamed[COLS["real_cut"]].sum() == base_frame[COLS["real_cut"]].sum()
    assert base_fingerprint(renamed) != base_fingerprint(base_frame)


def test_fingerprint_detects_defect_type_rename(base_frame):
    renamed = base_frame.copy()
    renamed.loc[0, COLS["defect"]] = "PONTO ESTOURADO "
    assert base_fingerprint(renamed) != base_fingerprint(base_frame)


def test_fingerprint_detects_append_and_removal(base_frame):
    """Import diário (append) e cobrança emitida (remoção de linhas)."""
    appended = pd.concat([base_frame, base_frame.tail(1)], ignore_index=True)
    assert base_fingerprint(appended) != base_fingerprint(base_frame)

    removed = base_frame.head(3)
    assert base_fingerprint(removed) != base_fingerprint(base_frame)


def test_fingerprint_detects_value_correction(base_frame):
    corrected = base_frame.copy()
    corrected.loc[0, COLS["quantity"]] = 41
    assert base_fingerprint(corrected) != base_fingerprint(base_frame)


# ── Métricas e ranking ────────────────────────────────────────────────────────

def test_supplier_summary_and_metrics(base_frame):
    dataset = build_dataset(base_frame)
    summary = AnalyticsService.supplier_summary(dataset.orders, target=0.95)

    oficina_a = summary.loc[summary["supplier"] == "OFICINA A"].iloc[0]
    assert oficina_a["orders"] == 2
    assert oficina_a["real_cut"] == 1500          # 1000 (OM 1001) + 500 (OM 1002)
    assert oficina_a["defect_pieces"] == 110
    assert oficina_a["defect_cost"] == 132.0

    metrics = AnalyticsService.metrics(dataset.orders, target=0.95)
    assert metrics.orders == 3
    assert metrics.real_cut == 1600               # 1500 + 100 da OFICINA B
    assert metrics.defect_pieces == 112
    assert metrics.performance == pytest.approx((1600 - 112) / 1600)
    assert metrics.defect_cost == pytest.approx(135.5)


def test_status_follows_the_chosen_target(base_frame):
    dataset = build_dataset(base_frame)

    strict = AnalyticsService.supplier_summary(dataset.orders, target=0.99)
    assert (strict["status"] == "Abaixo da meta").all()

    loose = AnalyticsService.supplier_summary(dataset.orders, target=0.50)
    assert (loose["status"] == "Dentro da meta").all()


def test_metrics_on_empty_orders_do_not_crash():
    metrics = AnalyticsService.metrics(pd.DataFrame(), target=0.9)
    assert metrics.suppliers == 0
    assert metrics.defect_cost == 0
    assert metrics.worst_supplier == "—"


# ── Filtros ───────────────────────────────────────────────────────────────────

def test_filter_by_date_reaggregates_the_partial_order(base_frame):
    """Recortar metade de uma OM não pode trazer o real cortado inteiro do período.

    A OM 1001 tem linhas em 01/06 e 02/06. Filtrando só o dia 01, a ordem deve
    ser recontada com o que sobrou — 40 peças perdidas, não 100.
    """
    dataset = build_dataset(base_frame)
    filtered = AnalyticsService.filter_dataset(
        dataset,
        start_date=pd.Timestamp("2026-06-01").date(),
        end_date=pd.Timestamp("2026-06-01").date(),
    )

    assert len(filtered.orders) == 1
    order = filtered.orders.iloc[0]
    assert order["master_order"] == "1001"
    assert order["real_cut"] == 1000
    assert order["defect_pieces"] == 40


def test_filter_by_supplier(base_frame):
    dataset = build_dataset(base_frame)
    filtered = AnalyticsService.filter_dataset(dataset, suppliers=["OFICINA B"])

    assert filtered.orders["supplier"].unique().tolist() == ["OFICINA B"]
    assert len(filtered.orders) == 1


def test_critical_orders_respect_the_threshold(base_frame):
    dataset = build_dataset(base_frame)

    # OM 1001 = 10% de perda, OM 1002 = 2%, OM 1003 = 2%.
    assert len(AnalyticsService.critical_orders(dataset.orders, 0.10)) == 1
    assert len(AnalyticsService.critical_orders(dataset.orders, 0.01)) == 3
    assert AnalyticsService.critical_orders(dataset.orders, 0.99).empty


def test_defect_breakdown_uses_rows_not_orders(base_frame):
    dataset = build_dataset(base_frame)
    breakdown = AnalyticsService.defect_breakdown(dataset.rows)

    top = breakdown.iloc[0]
    assert top["defect_type"] == "SEM ARREMATE"   # 60 peças, o maior isolado
    assert breakdown["share"].sum() == pytest.approx(1.0)


def test_performance_trend_groups_by_period(base_frame):
    dataset = build_dataset(base_frame)

    monthly = AnalyticsService.performance_trend(dataset.orders, "month")
    assert monthly["period"].tolist() == ["2026-06"]

    weekly = AnalyticsService.performance_trend(dataset.orders, "week")
    assert not weekly.empty


# ── Exportações ───────────────────────────────────────────────────────────────

def test_exports_produce_valid_files(base_frame):
    dataset = build_dataset(base_frame)
    summary = AnalyticsService.supplier_summary(dataset.orders, 0.9)
    critical = AnalyticsService.critical_orders(dataset.orders, 0.05)

    excel = SupplierExportService.build_excel(summary, 0.9, "01/06/2026 a 03/06/2026")
    assert excel[:2] == b"PK"

    ranking_pdf = SupplierExportService.build_pdf(summary, 0.9, "01/06/2026 a 03/06/2026")
    assert ranking_pdf[:4] == b"%PDF"

    orders_pdf = PdfReportService.build(critical, summary, 0.9, 0.05, "01/06/2026")
    assert orders_pdf[:4] == b"%PDF"


def test_exports_handle_empty_selection():
    empty_summary = AnalyticsService.supplier_summary(pd.DataFrame())
    empty_orders = pd.DataFrame(columns=empty_summary.columns)

    assert SupplierExportService.build_excel(empty_summary, 0.9, "—")[:2] == b"PK"
    assert SupplierExportService.build_pdf(empty_summary, 0.9, "—")[:4] == b"%PDF"
    assert PdfReportService.build(empty_orders, empty_summary, 0.9, 0.1, "—")[:4] == b"%PDF"
