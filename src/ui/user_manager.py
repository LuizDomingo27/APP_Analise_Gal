# -*- coding: utf-8 -*-
"""
UI do painel de Gerenciamento de Usuários — módulo isolado.

Versão com design moderno e coerente, utilizando as mesmas especificações de 
formulário do editor de registros (degradê suave, borda verde-água, 
sombras de destaque e subseções com divisores).
"""

from datetime import datetime
import streamlit as st
from src.auth import auth_db
from src.auth import session
from src.config.settings import COLORS
from src.data.database import DatabaseUnavailableError


def _inject_custom_styles() -> None:
    """Injeta estilos CSS personalizados para uma interface premium, incluindo o padrão do editor."""
    st.markdown(
        f"""
        <style>
        /* ── Card de Usuário ── */
        div[data-testid="stVerticalBlock"] > div[class*="st-key-user_card_"] {{
            background: #FFFFFF !important;
            border: 1px solid rgba(0,184,132,0.08) !important;
            border-radius: 14px !important;
            padding: 14px 20px !important;
            margin-bottom: 12px !important;
            box-shadow: 0 4px 12px rgba(0,184,132,0.02) !important;
            transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }}
        div[data-testid="stVerticalBlock"] > div[class*="st-key-user_card_"]:hover {{
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 24px rgba(0,184,132,0.07) !important;
            border-color: rgba(0,184,132,0.22) !important;
        }}

        /* ── Card do Formulário (Padrão do Editor de Registros) ── */
        div[class*="st-key-form_container"] {{
            background: linear-gradient(160deg, #FFFFFF 0%, #F2F7F5 100%) !important;
            border: 1px solid rgba(0,229,160,0.30) !important;
            border-top: 3px solid #00B884 !important;
            border-radius: 14px !important;
            padding: 20px 22px 14px !important;
            box-shadow: 0 0 24px rgba(0,229,160,0.08), 0 2px 10px rgba(0,0,0,0.04) !important;
        }}
        div[class*="st-key-form_container"] [data-testid="stForm"] {{
            border: none !important;
            padding: 0 !important;
        }}
        div[class*="st-key-form_container"] label p {{
            font-size: 12px !important;
            font-weight: 600 !important;
            color: {COLORS['text_muted']} !important;
        }}
        
        /* ── Botão de Excluir Personalizado ── */
        div[class*="st-key-del_btn_"] button {{
            background: rgba(226, 75, 74, 0.08) !important;
            color: #E24B4A !important;
            border: 1px solid rgba(226, 75, 74, 0.15) !important;
            border-radius: 8px !important;
            transition: all 0.15s ease !important;
            height: 38px !important;
            width: 38px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 0 !important;
            margin-top: 4px !important;
        }}
        div[class*="st-key-del_btn_"] button:hover {{
            background: #E24B4A !important;
            color: #FFFFFF !important;
            border-color: #E24B4A !important;
            box-shadow: 0 4px 12px rgba(226, 75, 74, 0.25) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


def _render_header() -> None:
    st.markdown(
        f"""
        <div style="padding:0.5rem 0 1.2rem;border-bottom:1px solid rgba(0,0,0,0.06);margin-bottom:1.8rem">
            <div style="display:flex;align-items:baseline;gap:12px">
                <span style="font-size:26px;font-weight:700;color:{COLORS['text_primary']}">👥 Gerenciamento de Usuários</span>
                <span style="font-size:12px;color:#00805C;background:rgba(0,229,160,0.18);
                             padding:3px 10px;border-radius:20px;border:1px solid rgba(0,229,160,0.3);font-weight:600">
                    Painel Administrativo
                </span>
            </div>
            <p style="color:{COLORS['text_muted']};font-size:13.5px;margin:5px 0 0">
                Cadastre novos colaboradores, defina níveis de acesso ou remova usuários do sistema.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_form_group_label(text: str) -> None:
    st.markdown(
        f"""
        <p style="font-size:10px;color:{COLORS['primary']};font-weight:700;
                  text-transform:uppercase;letter-spacing:0.8px;margin:0 0 10px">
            {text}
        </p>
        """,
        unsafe_allow_html=True,
    )


def _render_form_divider() -> None:
    st.markdown(
        "<hr style='margin:2px 0 14px;border:none;border-top:1px solid rgba(0,0,0,0.07)'>",
        unsafe_allow_html=True,
    )


def _format_date(iso_str: str) -> str:
    """Formata a data ISO para exibição mais limpa (DD/MM/YYYY às HH:MM)."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return iso_str


def _render_user_manager_page_inner() -> None:
    _inject_custom_styles()
    _render_header()

    current_user = session.current_user() or {}
    users = auth_db.list_users()

    # ── Formulário — centralizado ao meio da tela, no mesmo card/estilo do
    #    editor de registros (degradê, borda verde-água, sombra de destaque) ──
    _, col_form, _ = st.columns([1, 2, 1])
    with col_form:
        with st.container(key="form_container"):
            _render_form_group_label("✦ Identificação e Acesso")

            # Exibe feedbacks do formulário
            form_error = st.session_state.pop("user_form_error", None)
            form_success = st.session_state.pop("user_form_success", None)

            if form_error:
                st.error(form_error)
            if form_success:
                st.success(form_success)

            with st.form("form_create_user", border=False, clear_on_submit=True):
                new_username = st.text_input(
                    "👤 Nome de usuário (login)",
                    placeholder="ex: maria.silva",
                    help="Use apenas letras minúsculas, números, pontos ou traços (3 a 32 caracteres)."
                )
                new_nome = st.text_input(
                    "✍️ Nome completo",
                    placeholder="ex: Maria Silva"
                )

                _render_form_divider()
                _render_form_group_label("✦ Segurança e Perfil")

                new_password = st.text_input(
                    "🔒 Senha provisória",
                    type="password",
                    placeholder="mínimo de 6 caracteres"
                )
                new_role = st.selectbox(
                    "🛡️ Perfil de Acesso",
                    ["user", "admin"],
                    format_func=lambda x: "Administrador (Acesso total)" if x == "admin" else "Usuário Comum"
                )

                st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
                submit = st.form_submit_button("💾 Criar Usuário", type="primary", use_container_width=True)

            if submit:
                ok, msg = auth_db.create_user(
                    username=new_username,
                    nome=new_nome,
                    password=new_password,
                    role=new_role
                )
                if ok:
                    st.session_state["user_form_success"] = msg
                    st.session_state.pop("confirm_delete", None)  # Limpa exclusão pendente se houver
                    st.rerun()
                else:
                    st.session_state["user_form_error"] = msg
                    st.rerun()

    # ── Lista de usuários cadastrados — abaixo do formulário, largura total ──
    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
    st.markdown("### 📋 Usuários Cadastrados")

    # Mensagem de confirmação de exclusão
    confirm_del = st.session_state.get("confirm_delete")
    if confirm_del:
        st.markdown(
            f"""
            <div style="
                background: rgba(226, 75, 74, 0.05);
                border: 1px solid rgba(226, 75, 74, 0.18);
                border-radius: 12px;
                padding: 16px 20px;
                margin-bottom: 20px;
            ">
                <h4 style="margin:0 0 6px; color:#E24B4A; font-size:14px; font-weight:700;">⚠️ Confirmação de Exclusão</h4>
                <p style="margin:0 0 12px; font-size:13px; color:#4A5752; line-height:1.5;">
                    Tem certeza que deseja remover o usuário <b>@{confirm_del}</b>? Esta ação removerá de imediato o acesso dele ao sistema.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("Sim, remover", type="primary", key="confirm_del_yes"):
                ok, msg = auth_db.delete_user(confirm_del)
                if ok:
                    st.session_state["user_form_success"] = msg
                    st.session_state.pop("confirm_delete", None)
                    st.rerun()
                else:
                    st.error(msg)
        with c2:
            if st.button("Cancelar", key="confirm_del_no"):
                st.session_state.pop("confirm_delete", None)
                st.rerun()
        st.markdown("<hr style='margin:18px 0'>", unsafe_allow_html=True)

    if not users:
        st.info("Nenhum usuário cadastrado no sistema.")
    else:
        # Lista com os cartões elegantes de usuários
        for idx, u in enumerate(users):
            with st.container(key=f"user_card_{u['username']}"):
                cols = st.columns([1, 7, 1])

                # Avatar circular com gradiente baseado nas iniciais
                with cols[0]:
                    initial = (u["nome"].strip()[:1] or "U").upper()
                    st.markdown(
                        f"""
                        <div style="
                            width: 44px; height: 44px;
                            border-radius: 50%;
                            background: linear-gradient(135deg, #00E5A0, #00B884);
                            color: #04231B; font-weight: 800; font-size: 16px;
                            display: flex; align-items: center; justify-content: center;
                            box-shadow: 0 2px 8px rgba(0,184,132,0.18);
                            margin-top: 2px;
                        ">{initial}</div>
                        """,
                        unsafe_allow_html=True
                    )

                # Nome, Username, Perfil e Data de Criação
                with cols[1]:
                    # Badge de perfil
                    if u["role"] == "admin":
                        badge_style = "background-color:rgba(0,184,132,0.12); color:#00805C; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700; margin-left:8px;"
                        badge_text = "Admin"
                    else:
                        badge_style = "background-color:rgba(124,137,133,0.10); color:#4A5752; padding:2px 8px; border-radius:10px; font-size:11px;"
                        badge_text = "Usuário"

                    st.markdown(
                        f"""
                        <div style="line-height: 1.35; padding-top: 1px;">
                            <span style="font-size: 15px; font-weight: 700; color: #0D1B17;">{u['nome']}</span>
                            <span style="{badge_style}">{badge_text}</span>
                            <div style="font-size: 12px; color: #7C8985; margin-top: 3px;">
                                <span>@{u['username']}</span>
                                <span style="margin: 0 6px; opacity: 0.5;">·</span>
                                <span>Criado em {_format_date(u['created_at'])}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # Ações de exclusão
                with cols[2]:
                    if u["username"] == current_user.get("username"):
                        st.markdown(
                            "<div style='font-size:11px; color:#7C8985; font-style:italic; text-align:center; padding-top:14px;'>Você</div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.button(
                            "🗑️",
                            key=f"del_btn_{u['username']}_{idx}",
                            help=f"Remover usuário {u['nome']}"
                        )


def render_user_manager_page() -> None:
    """Ponto de entrada público — protege a página contra falhas de banco,
    mostrando uma mensagem amigável em vez de um traceback cru."""
    try:
        _render_user_manager_page_inner()
    except DatabaseUnavailableError as exc:
        st.error(f"⚠️ {exc}")
