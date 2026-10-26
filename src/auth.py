"""Authentication with bundled access; explicit Streamlit Secrets take priority."""
from __future__ import annotations

from pathlib import Path
import time
import tomllib

import streamlit as st

from src.security import LoginThrottle, hash_password, verify_password

ROOT = Path(__file__).resolve().parents[1]


@st.cache_resource(show_spinner=False)
def _throttle():
    return LoginThrottle()


@st.cache_resource(show_spinner=False)
def _dummy_hash():
    # Equal work for unknown users. This random dummy is never a login account.
    import secrets
    return hash_password(secrets.token_urlsafe(32))


def _config() -> dict:
    # The ready-to-deploy package includes the admin account requested by the
    # owner. An explicit auth table in Secrets replaces the bundled accounts,
    # even when it is empty, so disabled access cannot silently fall back.
    try:
        if "auth" in st.secrets:
            return dict(st.secrets["auth"])
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    path = ROOT / "config" / "access.toml"
    if not path.exists():
        return {}
    return dict(tomllib.loads(path.read_text(encoding="utf-8")).get("auth", {}))


def logout():
    for key in list(st.session_state):
        del st.session_state[key]
    st.rerun()


@st.cache_data(show_spinner=False)
def _login_map() -> str:
    """Ecuador in the institutional night ramp; the welcome image of the system.

    Only the province outline order is used here, never figures: the login
    screen shows no data before authentication.
    """
    from src import geo, theme
    codes = [code for code in geo.features("provincia") if code != geo.NO_POLYGON]
    tones = theme.NIGHT_SEQUENTIAL[1:6]
    fills = {code: tones[i % len(tones)] for i, code in enumerate(codes)}
    return geo.svg_map(fills, stroke=theme.MORADO_900)


def _login_layout():
    from src.ui import icon, logo_data
    logo = f'<img class="brand-logo" src="{logo_data()}" alt="Gobierno del Ecuador · Ministerio de Trabajo y Desarrollo Humano"/>' if logo_data() else ""
    band = st.container(key="login_band", vertical_alignment="center")
    with band:
        left, right = st.columns([1.25, 1], gap="large", vertical_alignment="center")
        with left:
            st.markdown(
                f'<div class="login-copy">{logo}<h1>InfoReport</h1>'
                '<p>Indicadores institucionales por periodo, ámbito y territorio, con reportes listos para compartir.</p>'
                '<p class="login-slogan"><b>El corazón de Ecuador.</b> Velamos por la calidad de vida de los ecuatorianos</p>'
                f'<div class="login-map">{_login_map()}</div></div>',
                unsafe_allow_html=True,
            )
        card = right.container(key="login_card")
        with card:
            st.markdown(
                f'<div class="login-head"><span class="lock">{icon("lock", 24)}</span><h2>Acceso a InfoReport</h2>'
                '<p>Ingrese con la cuenta autorizada por la dirección responsable de la información.</p></div>',
                unsafe_allow_html=True,
            )
    return card


def require_login() -> dict:
    config = _config()
    users = dict(config.get("users", {}))
    now = time.monotonic()
    session = st.session_state.get("_auth_session")
    if session:
        username = session["username"]
        record = dict(users.get(username, {}))
        valid_record = record and record.get("enabled", True)
        same_hash = record.get("password_hash", "") == session.get("credential_version")
        idle = max(5, int(config.get("idle_minutes", 30))) * 60
        lifetime = max(1, int(config.get("max_hours", 8))) * 3600
        if valid_record and same_hash and now - session["last_seen"] <= idle and now - session["issued"] <= lifetime:
            session["last_seen"] = now
            return {"username": username, "name": str(record.get("name", username)), "role": str(record.get("role", "viewer"))}
        for key in list(st.session_state):
            del st.session_state[key]

    card = _login_layout()
    with card:
        if not users:
            st.info("Configure la cuenta de acceso para comenzar.")
            st.markdown("Ejecute **`python scripts/configure_auth.py`** en su equipo. En Streamlit Cloud, copie el archivo generado en "
                        "**Settings → Secrets**. La guía está en el README del proyecto.")
            st.caption("El acceso permanece cerrado hasta configurar una cuenta.")
            st.stop()
        with st.form("login_form", clear_on_submit=True, border=False):
            username = st.text_input("Usuario", placeholder="Usuario", max_chars=80, autocomplete="username",
                                     icon=":material/person:").strip().casefold()
            password = st.text_input("Contraseña", type="password", placeholder="Contraseña", max_chars=256,
                                     autocomplete="current-password", icon=":material/lock:")
            submitted = st.form_submit_button("Ingresar al sistema", type="primary", width="stretch", icon=":material/login:")
        if submitted:
            throttle = _throttle()
            remaining = throttle.remaining(username)
            if remaining:
                st.error(f"Demasiados intentos. Intente nuevamente en {remaining} segundos.")
            else:
                record = dict(users.get(username, {}))
                encoded = record.get("password_hash", _dummy_hash())
                valid = verify_password(password, encoded)
                if record and record.get("enabled", True) and valid:
                    throttle.success(username)
                    st.session_state["_auth_session"] = {"username": username, "issued": now, "last_seen": now, "credential_version": encoded}
                    st.rerun()
                else:
                    throttle.failure(username)
                    st.error("Usuario o contraseña incorrectos.")
        from src.ui import icon
        idle_minutes = max(5, int(config.get("idle_minutes", 30)))
        st.markdown(f'<div class="login-foot">{icon("shield", 16)}<span>Sesión protegida. Se cierra tras {idle_minutes} minutos sin actividad.</span></div>',
                    unsafe_allow_html=True)
    st.stop()
