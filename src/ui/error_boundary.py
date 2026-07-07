# -*- coding: utf-8 -*-
"""
Fronteira de erros (error boundary) das páginas Streamlit.

A camada de dados (src/data/database.py) já traduz qualquer falha do
Postgres/Supabase — conexão recusada, timeout, tabela/coluna inexistente,
DATABASE_URL ausente etc. — em `DatabaseUnavailableError`, com uma mensagem
em português segura de exibir ao usuário final.

Este módulo garante que essa exceção seja capturada na fronteira de cada
página (o `main()` de cada arquivo em pages/ e o app.py), mostrando um aviso
amigável em vez de um traceback cru do Streamlit.

IMPORTANTE: capturamos SOMENTE `DatabaseUnavailableError`. Não capturamos
`Exception` genérico aqui de propósito — o controle de fluxo do Streamlit
(`st.stop()` → StopException, `st.rerun()` → RerunException) é feito via
exceções, e engoli-las quebraria o login e os botões da aplicação.
`DatabaseUnavailableError` é subclasse de `RuntimeError` e não colide com
essas exceções de controle.
"""

import functools

import streamlit as st

from src.data.database import DatabaseUnavailableError


def render_db_error(exc: Exception) -> None:
    """Exibe a mensagem amigável de indisponibilidade do banco."""
    st.error(f"⚠️ {exc}")
    st.caption(
        "Se o problema persistir, atualize a página em instantes ou contate o suporte."
    )


def page_guard(fn):
    """
    Decorator para o `main()` de uma página: captura falhas de banco e mostra
    uma mensagem amigável, sem interromper o control-flow do Streamlit.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DatabaseUnavailableError as exc:
            render_db_error(exc)
    return wrapper
