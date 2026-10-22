"""Small, reusable presentation components for the institutional interface."""
from __future__ import annotations

import base64
import html
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PURPLE = "#512F8D"
FUCHSIA = "#C33F8D"
NAVY = "#192642"

SECTIONS = {
    "bonos_pensiones": "Bonos y pensiones",
    "proteccion_integral": "Servicios de protección integral",
}

_PATHS = {
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="11" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="18" width="7" height="3" rx="1"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/><circle cx="9" cy="7" r="4"/>',
    "wallet": '<path d="M20 8V5a2 2 0 0 0-2-2H6a3 3 0 0 0 0 6h14v12H6a3 3 0 0 1-3-3V6m17 7h-5v4h5"/>',
    "building": '<path d="M3 21h18M5 21V5l7-3 7 3v16M9 21v-5h6v5M9 7h.01M15 7h.01M9 11h.01M15 11h.01"/>',
    "chart": '<path d="M3 3v18h18M7 16v-4m5 4V7m5 9v-6"/>',
    "shield": '<path d="M12 22s9-4 9-11V4l-9-3-9 3v7c0 7 9 11 9 11zM8 11l3 3 5-5"/>',
    "document": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6"/>',
    "presentation": '<path d="M3 3h18M4 3v13h16V3M12 16v5m-4 1 4-1 4 1M8 11V9m4 2V6m4 5V8"/>',
    "pin": '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0z"/><circle cx="12" cy="10" r="2.5"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
}


def icon(name: str, size: int = 22, color: str = "currentColor") -> str:
    """Return trusted, application-owned SVG; user text never enters paths."""
    path = _PATHS.get(name, _PATHS["chart"])
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'


def inject_styles() -> None:
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def number(value: object, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def money(value: object, compact: bool = False) -> str:
    if value is None or pd.isna(value):
        return "No disponible"
    if compact:
        return f"{number(float(value) / 1_000_000, 2)} M"
    return f"USD {number(value, 2)}"


def pretty_label(text: str) -> str:
    """Province casing, with accents preserved from the data model."""
    return str(text).title().replace(" De ", " de ").replace(" Del ", " del ").replace(" Y ", " y ")


def image_data(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def hero(period: str, territory: str) -> None:
    logo = ROOT / "assets" / "brand" / "mtdh_logo.png"
    brand = f'<img src="{image_data(logo)}" alt="Ministerio de Trabajo y Desarrollo Humano"/>' if logo.exists() else '<span>Ministerio de Trabajo y Desarrollo Humano</span>'
    st.markdown(
        f'<div class="institutional-hero"><div class="hero-copy"><div class="hero-eyebrow">ESTADÍSTICA INSTITUCIONAL</div>'
        f'<h1>Evidencia para mejores decisiones.</h1><p>Protección social en cifras, con una visión integral del territorio.</p>'
        f'<div class="hero-meta"><span>{icon("calendar", 15)} {html.escape(period)}</span><span>{icon("pin", 15)} {html.escape(territory)}</span></div></div>'
        f'<div class="hero-brand">{brand}<div class="brand-rule"></div><span>Ministerio de Trabajo<br/>y Desarrollo Humano</span></div></div>',
        unsafe_allow_html=True,
    )


def metric(label: str, value: str, note: str, symbol: str = "chart", tone: str = "purple", prefix: str = "") -> None:
    st.markdown(
        f'<div class="metric-card {tone}"><div class="metric-top"><span>{html.escape(label)}</span><div class="metric-icon">{icon(symbol, 21)}</div></div>'
        f'<div class="metric-value"><small>{html.escape(prefix)}</small>{html.escape(value)}</div><div class="metric-note">{html.escape(note)}</div></div>',
        unsafe_allow_html=True,
    )


def section_heading(title: str, subtitle: str = "", symbol: str = "chart", eyebrow: str = "") -> None:
    eyebrow_html = f'<div class="section-eyebrow">{html.escape(eyebrow)}</div>' if eyebrow else ""
    sub = f'<p>{html.escape(subtitle)}</p>' if subtitle else ""
    st.markdown(f'<div class="section-heading"><div class="section-icon">{icon(symbol)}</div><div>{eyebrow_html}<h2>{html.escape(title)}</h2>{sub}</div></div>', unsafe_allow_html=True)


def chart_title(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="chart-title"><h3>{html.escape(title)}</h3><p>{html.escape(subtitle)}</p></div>', unsafe_allow_html=True)


def info_note(text: str, label: str = "Lectura de los datos") -> None:
    st.markdown(f'<div class="data-note"><span class="data-note-label">{html.escape(label)}</span><span>{html.escape(text)}</span></div>', unsafe_allow_html=True)


def report_cover(title: str, period: str, scope: str, stats: dict, presentation: bool = False) -> None:
    label = "PRESENTACIÓN INSTITUCIONAL" if presentation else "BOLETÍN ESTADÍSTICO"
    logo = ROOT / "assets" / "brand" / "mtdh_logo.png"
    brand = f'<img src="{image_data(logo)}" alt="MTDH"/>' if logo.exists() else "MTDH"
    if "Bonos y pensiones" in scope and "Servicios" not in scope:
        c1, l1 = number(stats.get("beneficiarios", 0)), "Beneficiarios reportados"
        c2, l2 = money(stats.get("monto_fiscal"), True), "Monto fiscal · USD"
    elif "Servicios" in scope and "Bonos y pensiones" not in scope:
        c1, l1 = number(stats.get("usuarios_servicios", 0)), "Usuarios reportados"
        c2, l2 = number(stats.get("unidades")), "Unidades de atención"
    else:
        c1, l1 = number(stats.get("beneficiarios", 0)), "Beneficiarios reportados"
        c2, l2 = number(stats.get("usuarios_servicios", 0)), "Usuarios de servicios"
    st.markdown(
        f'<div class="report-cover {"landscape" if presentation else ""}"><div class="cover-head">{brand}</div>'
        f'<div class="cover-body"><div class="cover-kicker">{label}</div><div class="cover-rule"></div><h2>{html.escape(title)}</h2><div class="cover-date">{html.escape(period)}</div>'
        f'<p>{html.escape(scope)}</p><div class="cover-mini-grid"><div><strong>{c1}</strong><span>{l1}</span></div><div><strong>{c2}</strong><span>{l2}</span></div></div></div>'
        f'<div class="cover-footer">Evidencia para mejores decisiones <span>MTDH</span></div></div>',
        unsafe_allow_html=True,
    )


def footer(period: str, source: str) -> None:
    st.markdown(f'<div class="app-footer"><div><strong>MTDH · Estadística institucional</strong><span>{html.escape(source)}</span></div><div>{html.escape(period)}<br/><span>Cifras sujetas al alcance de la fuente</span></div></div>', unsafe_allow_html=True)
