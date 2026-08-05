# -*- coding: utf-8 -*-
"""Exceções da análise de performance, todas seguras de exibir ao usuário."""


class PerformanceError(Exception):
    """Base das falhas apresentáveis desta análise."""


class DataValidationError(PerformanceError):
    """A base carregada não pode ser analisada com segurança."""


class ReportGenerationError(PerformanceError):
    """Um relatório (PDF/Excel) não pôde ser gerado para o recorte atual."""
