# -*- coding: utf-8 -*-
"""Formatação numérica e de datas no padrão brasileiro."""

from __future__ import annotations

import math
import re
from datetime import date, datetime


PLACEHOLDER = "—"


def to_float(value: object) -> float | None:
    """Converte para float finito; devolve None para qualquer coisa inutilizável."""
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def number_br(value: float | int, decimals: int = 0) -> str:
    """1234.5 -> "1.234,5". Valor não numérico ou infinito vira travessão."""
    numeric = to_float(value)
    if numeric is None:
        return PLACEHOLDER
    text = f"{numeric:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def percent_br(value: float, decimals: int = 1) -> str:
    """0.9123 -> "91,2%". None/NA/texto viram travessão em vez de estourar."""
    numeric = to_float(value)
    if numeric is None:
        return PLACEHOLDER
    return f"{number_br(numeric * 100, decimals)}%"


def currency_br(value: float, decimals: int = 2) -> str:
    """1234.5 -> "R$ 1.234,50"."""
    if to_float(value) is None:
        return PLACEHOLDER
    return f"R$ {number_br(value, decimals)}"


def date_br(value: object) -> str:
    """Datas e strings ISO no formato dia/mês/ano, inclusive períodos "X a Y"."""
    if isinstance(value, (datetime, date)):
        try:
            return value.strftime("%d/%m/%Y")
        except ValueError:
            # pandas NaT herda de datetime mas recusa formatar.
            return PLACEHOLDER

    text = str(value).strip()
    if not text or text.lower() in {"nat", "nan", "none", "<na>"}:
        return PLACEHOLDER

    period_parts = text.split(" a ", maxsplit=1)
    if len(period_parts) == 2:
        return f"{date_br(period_parts[0])} a {date_br(period_parts[1])}"

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", text):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except ValueError:
            pass

    return text
