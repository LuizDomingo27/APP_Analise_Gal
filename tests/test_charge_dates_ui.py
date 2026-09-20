from datetime import date, timedelta

from streamlit.testing.v1 import AppTest


def _page():
    import streamlit as st
    from src.ui.cobranca import _render_charge_dates_input

    cobranca, vencimento, dias = _render_charge_dates_input("Oficina A")
    st.session_state["resultado_datas"] = (cobranca, vencimento, dias)


def _open(role):
    app = AppTest.from_function(_page, default_timeout=60)
    app.session_state["auth_user"] = {"username": "teste", "role": role}
    return app.run()


def test_admin_changes_term_and_charge_date():
    app = _open("admin")
    assert not app.exception
    assert app.number_input[0].value == 10
    assert not app.number_input[0].disabled
    cobranca = date(date.today().year, 12, 20)
    app.date_input[0].set_value(cobranca)
    app.number_input[0].set_value(30).run()
    assert not app.exception
    vencimento = cobranca + timedelta(days=30)
    assert app.session_state["resultado_datas"] == (
        cobranca, vencimento, (vencimento - date.today()).days,
    )
    assert vencimento.strftime("%d/%m/%Y") in " ".join(
        item.value for item in app.markdown
    )


def test_user_cannot_reuse_admin_term():
    app = _open("admin")
    app.number_input[0].set_value(45).run()
    app.session_state["auth_user"] = {"username": "comum", "role": "user"}
    app.run()
    assert not app.exception
    assert app.number_input[0].disabled
    assert app.number_input[0].value == 10
    cobranca, vencimento, _ = app.session_state["resultado_datas"]
    assert vencimento == cobranca + timedelta(days=10)


def test_zero_day_term_expires_on_charge_date():
    app = _open("admin")
    app.number_input[0].set_value(0).run()
    assert not app.exception
    cobranca, vencimento, _ = app.session_state["resultado_datas"]
    assert vencimento == cobranca
