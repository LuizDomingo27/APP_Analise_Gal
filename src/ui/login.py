# -*- coding: utf-8 -*-
"""
Tela de proteção (login) — identidade visual do app.

Renderiza a página de autenticação em tela cheia com três abas:
  • Entrar            — login com usuário e senha
  • Criar Conta       — auto-cadastro (o 1º usuário vira administrador)
  • Esqueci a Senha   — reset via pergunta de segurança

Também expõe render_admin_user_panel(): painel na sidebar, visível apenas
para administradores, para inserir e remover usuários.
"""

import streamlit as st

from src.auth import auth_db
from src.auth import session

# Perguntas de segurança pré-definidas (usadas no cadastro e no reset).
SECURITY_QUESTIONS = [
    "Qual o nome do seu primeiro animal de estimação?",
    "Em que cidade você nasceu?",
    "Qual o nome de solteira da sua mãe?",
    "Qual o nome da sua primeira escola?",
    "Qual o seu prato de comida favorito?",
]


# ── CSS da tela de login ──────────────────────────────────────────────────────

def _inject_login_css() -> None:
    st.markdown(
        """
        <style>
        /* Esconde a navegação/barra lateral enquanto não está logado */
        [data-testid="stSidebar"], [data-testid="stSidebarNav"],
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stAppViewContainer"] > .main { background: #FAFCFB; }
        [data-testid="stMain"]   { background: #FAFCFB; }
        [data-testid="stHeader"] { background: transparent !important; }
        /* Largura enxuta, padrão de formulário de login (não ocupa a tela toda) */
        .main .block-container {
            padding-top: 2.6rem;
            max-width: 400px !important;
            margin-left: auto;
            margin-right: auto;
        }

        /* Cartão de login — largura enxuta e centralizado (não ocupa a tela toda) */
        div[class*="st-key-login_card"] {
            width: 100% !important;
            max-width: 400px !important;
            margin: 8px auto 0 !important;
            background: #FFFFFF;
            border: 1px solid rgba(0,184,132,0.22);
            border-top: 4px solid #00B884;
            border-radius: 16px;
            padding: 26px 26px 22px;
            box-shadow: 0 18px 48px rgba(13,27,23,0.10),
                        0 0 0 1px rgba(0,229,160,0.05),
                        0 2px 8px rgba(0,0,0,0.03);
        }
        /* Rodapé/mensagens acompanham a mesma largura do cartão */
        .main .block-container { padding-top: 2.4rem; }

        /* Inputs padrão (borda verde da identidade) */
        .stTextInput input, .stSelectbox [data-baseweb="select"] > div,
        [data-baseweb="input"], [data-baseweb="select"] {
            background: #FFFFFF !important;
            color: #0D1B17 !important;
            border: 1px solid rgba(0,184,132,0.35) !important;
            border-radius: 8px !important;
        }
        .stTextInput input:hover,
        .stSelectbox [data-baseweb="select"] > div:hover {
            border-color:#0D1B17 !important;
            box-shadow: 0 0 0 2px rgba(0,229,160,0.15) !important;
        }
        .stTextInput input:focus {
            border-color:#0D1B17 !important;
            box-shadow: 0 0 0 2px rgba(0,229,160,0.25) !important;
            outline: none !important;
        }
        [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {
            background: #FFFFFF !important; color: #0D1B17 !important;
            border: 1px solid rgba(0,184,132,0.25) !important;
        }
        [data-baseweb="menu"] li, [role="option"] { color:#0D1B17 !important; background:#FFFFFF !important; }
        [data-baseweb="menu"] li:hover, [role="option"]:hover,
        [role="option"][aria-selected="true"] { background: rgba(0,229,160,0.15) !important; color:#0D1B17 !important; }
        [data-baseweb="select"] svg, [data-baseweb="input"] svg { fill:#00B884 !important; }
        .stTextInput label p, .stSelectbox label p {
            font-size: 12.5px !important; font-weight: 600 !important; color:#4A5752 !important;
        }

        /* Abas centralizadas */
        .stTabs [data-baseweb="tab-list"] { gap: 4px; justify-content: center; border-bottom: 1px solid rgba(0,184,132,0.18); }
        .stTabs [data-baseweb="tab"] { color:#4A5752 !important; font-size:13.5px !important; font-weight:600 !important; }
        .stTabs [data-baseweb="tab"][aria-selected="true"] { color:#00805C !important; }
        .stTabs [data-baseweb="tab-highlight"] { background:#00B884 !important; }

        /* Botões primários */
        .stButton > button, .stFormSubmitButton > button {
            background: #FFFFFF !important; color:#0D1B17 !important;
            border: 1px solid #00B884 !important; border-radius: 8px !important;
            font-size: 13px !important; font-weight: 600 !important;
            transition: all 0.18s ease !important;
        }
        .stButton > button:hover, .stFormSubmitButton > button:hover {
            background: rgba(0,229,160,0.18) !important; color:#00805C !important; border-color:#0D1B17 !important;
        }
        .stFormSubmitButton > button[kind="primaryFormSubmit"],
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg,#00C994,#00B884) !important;
            color:#FFFFFF !important; border:1px solid rgba(0,184,132,0.6) !important;
            font-weight: 700 !important;
        }
        .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover,
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg,#00B884,#00A578) !important; color:#FFFFFF !important;
        }
        [data-testid="stAlert"] { color:#0D1B17 !important; border-radius: 10px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_brand() -> None:
    st.markdown(
        """
        <div style="text-align:center; margin-bottom:18px">
            <div style="
                width:60px; height:60px; margin:0 auto 12px;
                border-radius:16px;
                background:linear-gradient(135deg,#00E5A0,#00B884);
                display:flex; align-items:center; justify-content:center;
                font-size:30px; box-shadow:0 8px 22px rgba(0,184,132,0.35);
            ">🔍</div>
            <div style="font-size:22px; font-weight:800; color:#0D1B17; letter-spacing:-0.3px">
                Análise de Defeitos
            </div>
            <div style="font-size:12.5px; color:#7C8985; margin-top:3px">
                Controle de Qualidade · Acesso restrito
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Abas ──────────────────────────────────────────────────────────────────────

def _render_login_tab() -> None:
    if auth_db.count_users() == 0:
        st.info(
            "👋 Nenhum usuário cadastrado ainda. Vá até **Criar Conta** — "
            "o primeiro cadastro será o administrador do sistema."
        )
        return

    with st.form("form_login", border=False):
        username = st.text_input("👤 Usuário", key="login_user",
                                 placeholder="seu.usuario")
        password = st.text_input("🔒 Senha", type="password", key="login_pass",
                                 placeholder="••••••••")
        submitted = st.form_submit_button("Entrar", type="primary",
                                          use_container_width=True)

    if submitted:
        ok, result = auth_db.authenticate(username, password)
        if ok:
            session.login(result)
            st.success(f"Bem-vindo(a), {result['nome']}!")
            st.rerun()
        else:
            st.error(result)


def _render_signup_tab() -> None:
    is_first = auth_db.count_users() == 0
    if is_first:
        st.markdown(
            "<div style='font-size:12px;color:#00805C;background:rgba(0,229,160,0.10);"
            "border:1px solid rgba(0,229,160,0.25);border-radius:8px;padding:8px 10px;"
            "margin-bottom:10px'>⭐ Este será o primeiro usuário e receberá acesso de "
            "<b>administrador</b>.</div>",
            unsafe_allow_html=True,
        )

    with st.form("form_signup", border=False):
        username = st.text_input("👤 Usuário", key="signup_user",
                                 placeholder="ex.: joao.silva")
        nome = st.text_input("📛 Nome completo", key="signup_nome",
                             placeholder="João da Silva")
        password = st.text_input("🔒 Senha", type="password", key="signup_pass",
                                 placeholder="mín. 6 caracteres")
        password2 = st.text_input("🔒 Confirmar senha", type="password",
                                  key="signup_pass2", placeholder="repita a senha")
        question = st.selectbox("🛡️ Pergunta de segurança", SECURITY_QUESTIONS,
                                key="signup_question")
        answer = st.text_input("✍️ Resposta de segurança", key="signup_answer",
                               placeholder="usada para recuperar a senha")
        submitted = st.form_submit_button("Criar Conta", type="primary",
                                          use_container_width=True)

    if submitted:
        if password != password2:
            st.error("As senhas não coincidem.")
            return
        if not (answer or "").strip():
            st.error("Informe a resposta de segurança (necessária para recuperar a senha).")
            return
        ok, msg = auth_db.create_user(
            username=username, nome=nome, password=password,
            security_question=question, security_answer=answer,
        )
        if ok:
            # Rerun para que a aba "Entrar" recarregue já com o novo usuário
            # contabilizado (a contagem muda no meio deste mesmo run).
            st.session_state["auth_flash"] = msg + " Vá até a aba **Entrar** para acessar."
            st.rerun()
        else:
            st.error(msg)


def _render_reset_tab() -> None:
    st.caption("Recupere o acesso respondendo à sua pergunta de segurança.")

    username = st.text_input("👤 Usuário", key="reset_user",
                             placeholder="seu.usuario")
    if st.button("Buscar pergunta de segurança", key="reset_lookup",
                 use_container_width=True):
        question = auth_db.get_security_question(username)
        if question is None:
            if auth_db.user_exists(username):
                st.session_state["reset_error"] = (
                    "Este usuário não configurou pergunta de segurança. "
                    "Peça a um administrador para redefinir a senha."
                )
                st.session_state.pop("reset_question", None)
            else:
                st.session_state["reset_error"] = "Usuário não encontrado."
                st.session_state.pop("reset_question", None)
        else:
            st.session_state["reset_question"] = question
            st.session_state["reset_username"] = auth_db.normalize_username(username)
            st.session_state.pop("reset_error", None)

    if st.session_state.get("reset_error"):
        st.error(st.session_state["reset_error"])

    question = st.session_state.get("reset_question")
    if question and st.session_state.get("reset_username") == auth_db.normalize_username(username):
        with st.form("form_reset", border=False):
            st.markdown(
                f"<div style='font-size:12.5px;color:#4A5752;margin-bottom:6px'>"
                f"🛡️ <b>{question}</b></div>",
                unsafe_allow_html=True,
            )
            answer = st.text_input("✍️ Resposta", key="reset_answer")
            new_pass = st.text_input("🔒 Nova senha", type="password", key="reset_newpass",
                                     placeholder="mín. 6 caracteres")
            new_pass2 = st.text_input("🔒 Confirmar nova senha", type="password",
                                      key="reset_newpass2")
            submitted = st.form_submit_button("Redefinir senha", type="primary",
                                              use_container_width=True)
        if submitted:
            if new_pass != new_pass2:
                st.error("As senhas não coincidem.")
                return
            ok, msg = auth_db.reset_password_with_answer(
                st.session_state["reset_username"], answer, new_pass
            )
            if ok:
                for k in ("reset_question", "reset_username", "reset_error"):
                    st.session_state.pop(k, None)
                st.success(msg)
            else:
                st.error(msg)


# ── Tela principal ────────────────────────────────────────────────────────────

def render_login_screen() -> None:
    """Renderiza a tela de login em tela cheia (chamada pelo require_login)."""
    auth_db.create_users_table()
    _inject_login_css()

    with st.container(key="login_card"):
        _render_brand()
        flash = st.session_state.pop("auth_flash", None)
        if flash:
            st.success(flash)
        tab_login, tab_signup, tab_reset = st.tabs(
            ["🔑 Entrar", "🆕 Criar Conta", "❓ Esqueci a Senha"]
        )
        with tab_login:
            _render_login_tab()
        with tab_signup:
            _render_signup_tab()
        with tab_reset:
            _render_reset_tab()

    st.markdown(
        "<div style='text-align:center;margin-top:16px;font-size:11px;color:#7C8985'>"
        "🔒 Suas credenciais são protegidas com hash PBKDF2 + salt.</div>",
        unsafe_allow_html=True,
    )


# ── Painel admin (sidebar) ────────────────────────────────────────────────────

def render_admin_user_panel() -> None:
    """Painel na sidebar para inserir/remover usuários (somente admin)."""
    with st.sidebar.expander("👥 Gerenciar Usuários"):
        admin_flash = st.session_state.pop("admin_flash", None)
        if admin_flash:
            st.success(admin_flash)
        st.markdown(
            "<p style='font-size:11.5px;color:#4A5752;margin:0 0 8px'>"
            "Inserir novo usuário no sistema.</p>",
            unsafe_allow_html=True,
        )
        with st.form("form_admin_add_user", border=False):
            new_user = st.text_input("Usuário", key="admin_new_user",
                                     placeholder="ex.: maria.souza")
            new_nome = st.text_input("Nome completo", key="admin_new_nome")
            new_pass = st.text_input("Senha provisória", type="password",
                                     key="admin_new_pass")
            new_role = st.selectbox("Perfil", ["user", "admin"], key="admin_new_role")
            add_submitted = st.form_submit_button("➕ Inserir usuário",
                                                  use_container_width=True)
        if add_submitted:
            ok, msg = auth_db.create_user(
                username=new_user, nome=new_nome, password=new_pass,
                role=new_role,
            )
            if ok:
                st.session_state["admin_flash"] = msg
                st.rerun()
            else:
                st.error(msg)

        st.markdown("<hr style='margin:10px 0'>", unsafe_allow_html=True)
        st.markdown(
            "<p style='font-size:11.5px;color:#4A5752;margin:0 0 6px'>"
            "Usuários cadastrados:</p>",
            unsafe_allow_html=True,
        )
        users = auth_db.list_users()
        current = session.current_user() or {}
        for u in users:
            cols = st.columns([3, 1])
            with cols[0]:
                tag = " · admin" if u["role"] == "admin" else ""
                st.markdown(
                    f"<div style='font-size:11.5px;color:#0D1B17;padding-top:6px'>"
                    f"<b>{u['nome']}</b><br>"
                    f"<span style='color:#7C8985'>@{u['username']}{tag}</span></div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                if u["username"] != current.get("username"):
                    if st.button("🗑️", key=f"del_{u['username']}",
                                 help=f"Remover {u['username']}"):
                        ok, msg = auth_db.delete_user(u["username"])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
