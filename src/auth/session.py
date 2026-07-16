# -*- coding: utf-8 -*-
"""
Controle de sessão/login no Streamlit.

Fornece o "portão" require_login() usado como primeira instrução de cada
página protegida: se não houver usuário autenticado na sessão, renderiza a
tela de login e interrompe a execução da página (st.stop()). Também expõe
render_user_topbar() para mostrar o usuário logado no topo (navbar), junto
com o botão de sair.
"""

import streamlit as st

_SESSION_KEY = "auth_user"


# ── Estado de sessão ──────────────────────────────────────────────────────────

def current_user() -> dict | None:
    """Retorna o dict do usuário autenticado nesta sessão, ou None."""
    return st.session_state.get(_SESSION_KEY)


def is_authenticated() -> bool:
    return current_user() is not None


def login(user: dict) -> None:
    """Registra o usuário na sessão (sem hashes sensíveis)."""
    st.session_state[_SESSION_KEY] = {
        "username": user.get("username"),
        "nome": user.get("nome"),
        "role": user.get("role", "user"),
    }


def logout() -> None:
    st.session_state.pop(_SESSION_KEY, None)


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == "admin")


# ── Portão de proteção ────────────────────────────────────────────────────────

def require_login() -> dict:
    """
    Garante que há um usuário autenticado. Caso contrário, renderiza a tela
    de login e interrompe a página (st.stop()). Retorna o usuário logado.
    """
    user = current_user()
    if user is not None:
        return user

    # Import tardio evita import circular (login.py usa este módulo).
    from src.ui.login import render_login_screen

    render_login_screen()
    st.stop()


def require_admin() -> dict:
    """
    Garante que há um usuário autenticado E com papel de administrador.
    Usuários comuns recebem uma mensagem de acesso negado e a página é
    interrompida (st.stop()). Retorna o usuário logado.
    """
    user = require_login()
    if user.get("role") != "admin":
        st.error("Acesso negado. Esta página é restrita a administradores.")
        st.stop()
    return user


# ── Navbar (topo): usuário logado ─────────────────────────────────────────────

def render_user_topbar() -> None:
    """
    Exibe, no topo à direita, um chip com o usuário logado (avatar + nome) que
    abre um popover com o papel e o botão de sair. Substitui o antigo cartão da
    sidebar agora que a navegação usa uma navbar no topo
    (st.navigation(position="top")).
    """
    user = current_user()
    if user is None:
        return

    nome = user.get("nome") or user.get("username") or "Usuário"
    username = user.get("username", "")
    role = user.get("role", "user")
    role_label = "Administrador" if role == "admin" else "Usuário"
    initial = (nome.strip()[:1] or "U").upper()

    # Chip do usuário fixado no cabeçalho, alinhado à ESQUERDA. Com a navbar
    # centralizada (oke width:100% + justify-content:center), o lado esquerdo
    # fica livre e o chip não sobrepõe o primeiro link.
    st.markdown(
        """
        <style>
        .st-key-user_topbar {
            position: fixed;
            top: 0.5rem;
            left: 1rem;
            width: auto !important;
            z-index: 1000000;
        }
        .st-key-user_topbar [data-testid="stPopover"] { width: auto !important; }
        .st-key-user_topbar [data-testid="stPopover"] > div { width: auto !important; }
        .st-key-user_topbar button[data-testid="stPopoverButton"] {
            background: rgba(0,229,160,0.12) !important;
            border: 1px solid rgba(0,184,132,0.35) !important;
            border-radius: 999px !important;
            padding: 4px 14px !important;
            font-size: 12.5px !important;
            font-weight: 600 !important;
            color: #0D1B17 !important;
        }
        .st-key-user_topbar button[data-testid="stPopoverButton"]:hover {
            background: rgba(0,229,160,0.22) !important;
            border-color: #00B884 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="user_topbar"):
        with st.popover(f"👤 {nome}", use_container_width=False):
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:11px; padding:2px 0 6px">
                    <div style="
                        width:38px; height:38px; flex:0 0 38px;
                        border-radius:50%;
                        background:linear-gradient(135deg,#00E5A0,#00B884);
                        color:#04231B; font-weight:800; font-size:16px;
                        display:flex; align-items:center; justify-content:center;
                        box-shadow:0 2px 8px rgba(0,184,132,0.35);
                    ">{initial}</div>
                    <div style="min-width:0; line-height:1.25">
                        <div style="font-size:13.5px; font-weight:700; color:#0D1B17;
                                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis">
                            {nome}
                        </div>
                        <div style="font-size:10.5px; color:#4A5752; display:flex; gap:6px; align-items:center">
                            <span style="color:#00805C">●</span>
                            <span>@{username}</span>
                            <span style="opacity:0.5">·</span>
                            <span>{role_label}</span>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("🚪 Sair", key="logout_btn", use_container_width=True):
                logout()
                st.rerun()
