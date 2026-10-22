"""Exercise the guard as Streamlit runs it: no data before authentication."""
from streamlit.testing.v1 import AppTest

from src.security import hash_password


APP = '''
import streamlit as st
from src.auth import require_login, logout
st.set_page_config(layout="wide")
user = require_login()
st.success("PANEL_PROTEGIDO")
st.write(user["name"])
if st.button("Cerrar sesión"):
    logout()
'''


def test_login_wrong_password_then_success_then_logout():
    at = AppTest.from_string(APP, default_timeout=15)
    at.secrets['auth'] = {'users': {'auditor': {
        'name': 'Usuario de prueba', 'password_hash': hash_password('clave-de-prueba-muy-larga'), 'enabled': True,
    }}}
    at.run()
    assert not at.exception
    assert len(at.success) == 0
    at.text_input[0].set_value('auditor')
    at.text_input[1].set_value('incorrecta')
    at.button[0].click().run()
    assert len(at.success) == 0
    assert len(at.error) == 1
    at.text_input[0].set_value('auditor')
    at.text_input[1].set_value('clave-de-prueba-muy-larga')
    at.button[0].click().run()
    assert not at.exception
    assert at.success[0].value == 'PANEL_PROTEGIDO'
    at.button[0].click().run()
    assert not at.exception
    assert len(at.success) == 0
    assert len(at.text_input) == 2


def test_no_config_is_closed():
    at = AppTest.from_string(APP, default_timeout=15)
    at.secrets['auth'] = {}
    at.run()
    assert not at.exception
    assert len(at.success) == 0
    assert len(at.info) == 1
