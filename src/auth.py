"""Authentication with bundled access; explicit Streamlit Secrets take priority."""
from __future__ import annotations

import base64
from html import escape
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


def _login_hero():
    logo = ROOT / "assets" / "brand" / "mtdh_logo.png"
    img = ""
    if logo.exists():
        img = '<img class="access-logo" alt="Ministerio de Trabajo y Desarrollo Humano" src="data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode() + '">'
    st.markdown('''<style>
    [data-testid="stSidebar"]{display:none}
    .access-hero{position:relative;overflow:hidden;border-radius:26px;padding:38px 42px 44px;
      background:linear-gradient(125deg,#251547 0%,#4f2d89 62%,#8052b2 100%);color:white;min-height:490px;box-shadow:0 24px 64px #32165319}
    .access-hero:before{content:"";position:absolute;width:330px;height:330px;border:1px solid #ffffff20;border-radius:50%;right:-150px;bottom:-145px;box-shadow:0 0 0 48px #ffffff08,0 0 0 96px #ffffff05}
    .access-logo{width:min(410px,100%);margin-bottom:54px}
    .access-kicker{text-transform:uppercase;font-size:11px;letter-spacing:2.2px;font-weight:650;color:#dfcaed;margin-bottom:14px}
    .access-hero h1{font-size:46px!important;line-height:1.12!important;font-weight:750!important;color:#fff!important;letter-spacing:-1.5px!important;margin:0 0 22px!important;padding:0!important}
    .access-hero p{font-size:16px;line-height:1.65;color:#e7ddf3;max-width:450px}
    .access-pill{display:inline-block;padding:8px 12px;border:1px solid #ffffff35;border-radius:8px;font-size:11px;letter-spacing:.3px;margin-top:15px;margin-right:7px;color:#fff}
    .access-label{color:#8657ae;font-size:12px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;margin:14px 0 12px}
    .access-title{font-size:31px;font-weight:750;letter-spacing:-.8px;color:#241a3c;line-height:1.2;margin-bottom:12px}
    .access-copy{font-size:14px;line-height:1.6;color:#71667f;margin-bottom:26px}
    [data-testid="stForm"]{background:#ffffff;border:1px solid #ece5f2;border-radius:18px;padding:25px}
    @media(max-width:760px){.access-hero{min-height:300px;padding:28px}.access-logo{margin-bottom:25px}.access-hero h1{font-size:34px!important}}
    </style>''', unsafe_allow_html=True)
    left, right = st.columns([1.35, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(f'''<section class="access-hero">{img}<div class="access-kicker">Sistema de información estadística</div>
        <h1>Datos que orientan.<br>Decisiones que<br>transforman.</h1>
        <p>Explora la cobertura de bonos, pensiones y servicios de protección integral. Convierte las cifras en reportes para la gestión.</p>
        <span class="access-pill">Análisis territorial</span><span class="access-pill">Reportes institucionales</span></section>''', unsafe_allow_html=True)
    return right


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

    right = _login_hero()
    with right:
        st.markdown('<div class="access-label">Bienvenido a InfoReportes</div><div class="access-title">Tu espacio de análisis</div><div class="access-copy">Inicia sesión con tu cuenta autorizada para consultar el dashboard y preparar publicaciones.</div>', unsafe_allow_html=True)
        if not users:
            st.info("Configura la cuenta de acceso para comenzar.")
            st.markdown("Ejecuta **`python scripts/configure_auth.py`** en tu equipo. En Streamlit Cloud, copia el archivo generado en **Settings → Secrets**. La guía está en el README del proyecto.")
            st.caption("El acceso permanece cerrado hasta configurar una cuenta.")
            st.stop()
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("Usuario", placeholder="Tu usuario", max_chars=80).strip().casefold()
            password = st.text_input("Contraseña", type="password", placeholder="Tu contraseña", max_chars=256)
            submitted = st.form_submit_button("Ingresar al sistema  →", type="primary", use_container_width=True)
        if submitted:
            throttle = _throttle()
            remaining = throttle.remaining(username)
            if remaining:
                st.error(f"Demasiados intentos. Vuelve a intentar en {remaining} segundos.")
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
        st.caption("Sesión protegida · Acceso exclusivo para cuentas autorizadas")
    st.stop()
