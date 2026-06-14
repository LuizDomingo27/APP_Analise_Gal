# -*- coding: utf-8 -*-
"""
CNPJ validation and formatting utility.
"""

import re

def validate_cnpj(cnpj: str) -> bool:
    """
    Valida um número de CNPJ de acordo com a regra de dígitos verificadores.
    Aceita CNPJ com ou sem formatação.
    """
    digits = re.sub(r"\D", "", cnpj)
    if len(digits) != 14:
        return False
    if len(set(digits)) == 1:
        return False

    def _calc_digit(block, multipliers):
        total = sum(int(d) * m for d, m in zip(block, multipliers))
        r = total % 11
        return 0 if r < 2 else 11 - r

    m1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    m2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _calc_digit(digits[:12], m1)
    d2 = _calc_digit(digits[:13], m2)
    return int(digits[12]) == d1 and int(digits[13]) == d2


def format_cnpj(cnpj: str) -> str:
    """
    Formata um CNPJ cru (apenas dígitos) no padrão XX.XXX.XXX/XXXX-XX.
    Retorna o valor original se não contiver exatamente 14 dígitos.
    """
    d = re.sub(r"\D", "", cnpj)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return cnpj
