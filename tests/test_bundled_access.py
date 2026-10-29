"""Verify the unzip-and-upload workflow with no manual Secrets setup."""
from pathlib import Path
import tomllib

from streamlit.testing.v1 import AppTest

from src.security import verify_password

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_access_only_contains_requested_accounts():
    config = tomllib.loads((ROOT / "config" / "access.toml").read_text())
    users = config["auth"]["users"]
    assert set(users) == {"admin", "david.paguay", "geovanny.altamirano", "michael.gomez", "delegado"}
    assert verify_password("admin12345678", users["admin"]["password_hash"])
    assert users["admin"]["role"] == "admin"
    expected = {"david.paguay": "David Paguay", "geovanny.altamirano": "Geovanny Altamirano",
                "michael.gomez": "Michael Gómez", "delegado": "Delegado"}
    for username, name in expected.items():
        record = users[username]
        assert record["name"] == name
        assert record["role"] == "viewer"
        assert record["enabled"] is True
        assert record["password_hash"].startswith("pbkdf2_sha256$600000$")
        assert not verify_password("admin12345678", record["password_hash"])
    assert len({record["password_hash"] for record in users.values()}) == len(users)


def test_real_app_login_without_secrets():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=25)
    app.run()
    assert not app.exception
    assert len(app.text_input) == 2
    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("admin12345678")
    next(b for b in app.button if "Ingresar al sistema" in b.label).click().run()
    assert not app.exception
    assert any(b.label == "Salir" for b in app.button)
    assert app.segmented_control(key="workspace").value == "Tablero"
    assert app.session_state["_auth_session"]["username"] == "admin"


def test_explicit_empty_auth_disables_bundled_account():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15)
    app.secrets["auth"] = {}
    app.run()
    assert not app.exception
    assert not app.text_input
    assert not any(b.label == "Salir" for b in app.button)
