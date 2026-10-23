"""Presentation components for the institutional interface.

Every component returns trusted, application-owned HTML on a single line (so
Markdown never re-interprets it).  User or data text is always escaped.
"""
from __future__ import annotations

import base64
from functools import lru_cache
import html
from pathlib import Path

import pandas as pd
import streamlit as st

from src import names, theme

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "brand" / "mtdh_logo.png"
PRODUCT = "InfoReport"

# Lucide icon geometry (ISC license, see assets/icons/LICENSE).
_PATHS = {
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "hand-coins": '<path d="M11 15h2a2 2 0 1 0 0-4h-3c-.6 0-1.1.2-1.4.6L3 17"/><path d="m7 21 1.6-1.4c.3-.4.8-.6 1.4-.6h4c1.1 0 2.1-.4 2.8-1.2l4.6-4.4a2 2 0 0 0-2.75-2.91l-4.2 3.9"/><path d="m2 16 6 6"/><circle cx="16" cy="9" r="2.9"/><circle cx="6" cy="5" r="3"/>',
    "building": '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/>',
    "landmark": '<path d="M3 22h18"/><path d="M6 18v-7"/><path d="M10 18v-7"/><path d="M14 18v-7"/><path d="M18 18v-7"/><path d="M12 2 20 7H4z"/>',
    "banknote": '<rect width="20" height="12" x="2" y="6" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 12h.01M18 12h.01"/>',
    "coins": '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    "map": '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
    "pin": '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
    "chart": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h8"/><path d="M7 11h12"/><path d="M7 6h3"/>',
    "grid": '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    "table": '<path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/>',
    "sheet": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
    "document": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "presentation": '<path d="M2 3h20"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "swipe": '<path d="m18 8 4 4-4 4"/><path d="M2 12h20"/><path d="m6 8-4 4 4 4"/>',
    "award": '<path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526"/><circle cx="12" cy="8" r="6"/>',
    "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "briefcase": '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>',
    "file-check": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
    "user-check": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/>',
    "hourglass": '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
    "pie": '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
}


def icon(name: str, size: int = 22, color: str = "currentColor", stroke: float = 1.8) -> str:
    """Return trusted, application-owned SVG; user text never enters paths."""
    path = _PATHS.get(name, _PATHS["chart"])
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>')


def inject_styles() -> None:
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# --- Number formatting (Spanish conventions: 1.578.019 and 1.180,5) ----------

def number(value: object, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def millions(value: object, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return number(float(value) / 1_000_000, decimals)


def pct(value: object, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{number(value, decimals)} %"


def is_mobile() -> bool:
    """Phones and tablets, from the browser's User-Agent; desktop when unknown."""
    try:
        agent = st.context.headers.get("User-Agent", "") or ""
    except Exception:  # noqa: BLE001 - outside a browser session (tests)
        return False
    return any(token in agent for token in ("Mobi", "Android", "iPhone", "iPad"))


def place_name(text: object) -> str:
    """Readable place names from upper-case sources: SAN MIGUEL DE LOS BANCOS → San Miguel de los Bancos."""
    return names.place(text, short=False)


@lru_cache(maxsize=1)
def logo_data() -> str:
    """The official logo with its transparent margins trimmed for compact layouts."""
    if not LOGO.exists():
        return ""
    from io import BytesIO
    from PIL import Image
    image = Image.open(LOGO).convert("RGBA")
    box = image.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if box:
        pad = 6
        image = image.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(image.width, box[2] + pad), min(image.height, box[3] + pad)))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _counter_digits(group: str, pad: bool) -> str:
    """CSS counters for one digit group; padded groups keep their leading zeros."""
    value = int(group)
    if not pad:
        return f'<i class="ct" style="--v:{value}"></i>'
    if len(group) == 1:
        return f'<i class="ct" style="--v:{value}"></i>'
    if len(group) == 2:
        return f'<i class="ct z2" style="--v:{value}"></i>'
    head, tail = group[0], group[1:]
    return f'<i class="ct" style="--v:{int(head)}"></i><i class="ct z2" style="--v:{int(tail)}"></i>'


def animated(value: object, decimals: int = 0) -> str:
    """A number that counts up with CSS only; the final text stays readable.

    The animated digits are hidden from assistive technology and a visually
    hidden copy carries the exact value.  Without @property support the final
    value is shown immediately.
    """
    if value is None or pd.isna(value):
        return '<span class="num-na">—</span>'
    text = number(value, decimals)
    integer, _, fraction = text.partition(",")
    groups = integer.split(".")
    parts = []
    for index, group in enumerate(groups):
        if index:
            parts.append('<b class="sep">.</b>')
        parts.append(_counter_digits(group, pad=index > 0))
    if fraction:
        parts.append('<b class="sep">,</b>')
        parts.append(_counter_digits(fraction, pad=True))
    return f'<span class="num-anim" aria-hidden="true">{"".join(parts)}</span><span class="sr-only">{_esc(text)}</span>'


# --- Shell -----------------------------------------------------------------------

def brand_mark() -> None:
    logo = f'<img class="brand-logo" src="{logo_data()}" alt="Gobierno del Ecuador · Ministerio de Trabajo y Desarrollo Humano"/>' if logo_data() else ""
    st.markdown(
        f'<div class="brand-mark">{logo}<div class="brand-product"><strong>{PRODUCT}</strong><span>Indicadores estratégicos</span></div></div>',
        unsafe_allow_html=True,
    )


def user_chip(user_name: str) -> None:
    initials = "".join(part[0] for part in str(user_name).split()[:2]).upper() or "U"
    st.markdown(
        f'<div class="brand-user" title="{_esc(user_name)}"><span class="avatar">{_esc(initials)}</span>'
        f'<span class="who"><strong>{_esc(user_name)}</strong><small>Sesión activa</small></span></div>',
        unsafe_allow_html=True,
    )


def hero_copy(period: str, headline: str, lead: str) -> None:
    st.markdown(
        f'<div class="hero-copy"><div class="hero-period"><span class="pulse"></span>{_esc(period)}</div>'
        f'<h1>{_esc(headline)}</h1><p class="hero-lead">{_esc(lead)}</p></div>',
        unsafe_allow_html=True,
    )


def map_fills(values: dict[str, float], palette=None) -> dict[str, str]:
    """Colours of a choropleth: ordered classes of the ramp; empty or zero values keep the neutral fill."""
    palette = palette or theme.NIGHT_SEQUENTIAL
    codes = [c for c, v in values.items() if v is not None and v == v and v > 0]
    colors = theme.ramp([values[c] for c in codes], palette)
    return {c: col for c, col in zip(codes, colors) if col}


def hero_map(svg: str, label: str, *, selected: str = "", equator: bool = True) -> None:
    """The night map of the band with its key: what is mapped, the ramp, the selection and the equator."""
    steps = "".join(f'<i style="background:{c}"></i>' for c in theme.NIGHT_SEQUENTIAL)
    selected_key = f'<span class="key-sel"><i></i>{_esc(selected)}</span>' if selected else ""
    equator_key = '<span class="key-eq"><i></i>Latitud 0°</span>' if equator else ""
    st.markdown(
        f'<figure class="hero-map">{svg}<figcaption><span class="key-label">{_esc(label)}</span>'
        f'<span class="key-ramp"><small>Menor</small>{steps}<small>Mayor</small></span>{selected_key}{equator_key}'
        f'</figcaption></figure>',
        unsafe_allow_html=True,
    )


def svg_columns(values: list[float], labels: list[str], *, titles: list[str] | None = None, average: float | None = None,
                width: int = 640, height: int = 360, night: bool = True, css_class: str = "ec-columns",
                value_text=None) -> str:
    """Column chart drawn as SVG for the purple band (or a light miniature): one column per period, its figure on
    top, the mean as a dotted gold line."""
    value_text = value_text or (lambda v: number(v))
    titles = titles or [f"{l}: {value_text(v)}" for l, v in zip(labels, values)]
    top, bottom, side = 34, 30, 8
    peak = max(values or [1]) or 1
    slot = (width - 2 * side) / max(1, len(values))
    bar = slot * 0.62
    ink = "#EFE8FA" if night else theme.MORADO_900
    muted = "#CDBFE6" if night else "#6E6880"
    fill = theme.NIGHT_SEQUENTIAL[-2] if night else theme.SERIE_BONOS
    track = "rgba(255,255,255,.06)" if night else "#F1EEF6"
    columns, captions = [], []
    for index, (value, label, title) in enumerate(zip(values, labels, titles)):
        h = (height - top - bottom) * (value or 0) / peak
        x = side + index * slot + (slot - bar) / 2
        y = height - bottom - h
        delay = f"--d:{index * 0.06:.2f}s"
        columns.append(
            f'<g class="ec-col" style="{delay}"><title>{_esc(title)}</title>'
            f'<rect x="{x:.1f}" y="{top - 6}" width="{bar:.1f}" height="{height - bottom - top + 6:.1f}" rx="7" fill="{track}"/>'
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bar:.1f}" height="{h:.1f}" rx="7" fill="{fill}"/></g>')
        captions.append(
            f'<g class="ec-lab" style="{delay}">'
            f'<text x="{x + bar / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" fill="{ink}" class="v">{_esc(value_text(value))}</text>'
            f'<text x="{x + bar / 2:.1f}" y="{height - 8}" text-anchor="middle" fill="{muted}" class="m">{_esc(label)}</text></g>')
    line = ""
    if average:
        ay = height - bottom - (height - top - bottom) * average / peak
        line = (f'<line class="avg" x1="{side}" x2="{width - side}" y1="{ay:.1f}" y2="{ay:.1f}" stroke="{theme.ORO}" '
                f'stroke-dasharray="2 6" stroke-linecap="round"/>')
    # The mean runs over the columns and under their figures, so every figure stays legible where the line crosses it.
    return (f'<svg class="{css_class}" viewBox="0 0 {width} {height}" role="img" aria-label="Serie mensual" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(columns)}{line}{"".join(captions)}</svg>')


def hero_series(svg: str, label: str, average_label: str = "", *, narrow: str = "", narrow_note: str = "") -> None:
    """The series of the band; ``narrow`` is a version drawn for phones (larger type, shorter figures)."""
    average = f'<span class="key-eq"><i></i>{_esc(average_label)}</span>' if average_label else ""
    note = f'<span class="key-note">{_esc(narrow_note)}</span>' if narrow and narrow_note else ""
    body = f'<div class="series-wide">{svg}</div><div class="series-narrow">{narrow}</div>' if narrow else svg
    st.markdown(f'<figure class="hero-map hero-series">{body}<figcaption><span class="key-label">{_esc(label)}</span>{note}{average}'
                f'</figcaption></figure>', unsafe_allow_html=True)


def kpi_grid(cards: list[dict], *, overlap: bool = True) -> None:
    """Cards: label, value, decimals, prefix, suffix, note, icon, tone, share (or bar with bar_label for rates)."""
    items = []
    for i, card in enumerate(cards):
        share = card.get("bar", card.get("share"))
        share_html = ""
        if share is not None and share == share:
            width = max(0.0, min(100.0, float(share)))
            caption = card.get("bar_label") if "bar" in card else f'{pct(share)} {card.get("share_label", "del total nacional")}'
            share_html = (f'<div class="kpi-share"><div class="bar"><span style="--w:{width:.2f}%"></span></div>'
                          f'<small>{_esc(caption)}</small></div>')
        prefix = f'<small class="pre">{_esc(card["prefix"])}</small>' if card.get("prefix") else ""
        suffix = f'<small class="suf">{_esc(card["suffix"])}</small>' if card.get("suffix") else ""
        note = f'<p class="kpi-note">{_esc(card["note"])}</p>' if card.get("note") else ""
        items.append(
            f'<article class="kpi tone-{card.get("tone", "morado")}" style="--i:{i}"><header><span class="kpi-icon">{icon(card.get("icon", "chart"), 22)}</span>'
            f'<h3>{_esc(card["label"])}</h3></header><div class="kpi-value">{prefix}{animated(card["value"], card.get("decimals", 0))}{suffix}</div>'
            f'{note}{share_html}</article>'
        )
    css_class = "kpi-grid" if overlap else "kpi-grid kpi-inline"
    st.markdown(f'<section class="{css_class} n{len(cards)}" aria-label="Indicadores principales">{"".join(items)}</section>',
                unsafe_allow_html=True)


def reach_strip(tiles: list[dict]) -> None:
    """Territorial reach: for each level, the territories with the indicator and how many gather half of it.

    Tiles carry ``icon``, ``title`` (Provincias), ``count``, ``with_text`` (con beneficiarios), ``half`` and
    ``half_text`` (reúnen la mitad de los beneficiarios).  The gold share of the bar is that half's share of the
    territories: the shorter it is, the more concentrated the indicator.
    """
    items = []
    for i, tile in enumerate(tiles):
        count, half = tile["count"], tile["half"]
        width = half / count * 100 if count else 0
        items.append(
            f'<article class="reach" style="--i:{i}"><span class="ri">{icon(tile["icon"], 20)}</span>'
            f'<div class="rh"><h4>{_esc(tile["title"])}</h4><div class="rv">{_esc(number(count))}<small>{_esc(tile["with_text"])}</small></div></div>'
            f'<div class="rbar" role="img" aria-label="{_esc(number(half))} de {_esc(number(count))}"><span style="--w:{width:.2f}%"></span></div>'
            f'<p><b>{_esc(number(half))}</b> {_esc(tile["half_text"])}</p></article>')
    st.markdown(f'<section class="reach-strip n{len(tiles)}" aria-label="Alcance territorial">{"".join(items)}</section>',
                unsafe_allow_html=True)


def section_heading(title: str, subtitle: str = "", symbol: str = "chart", anchor: str = "") -> None:
    sub = f"<p>{_esc(subtitle)}</p>" if subtitle else ""
    anchor_attr = f' id="{_esc(anchor)}"' if anchor else ""
    st.markdown(f'<div class="section-heading"{anchor_attr}><span class="section-icon">{icon(symbol, 22)}</span><div><h2>{_esc(title)}</h2>{sub}</div></div>', unsafe_allow_html=True)


def chart_title(title: str, subtitle: str = "", badge: str = "") -> None:
    badge_html = f'<span class="card-badge">{_esc(badge)}</span>' if badge else ""
    st.markdown(f'<div class="card-title"><div><h3>{_esc(title)}</h3><p>{_esc(subtitle)}</p></div>{badge_html}</div>', unsafe_allow_html=True)


def info_note(text: str, label: str, tone: str = "info") -> None:
    st.markdown(f'<div class="note note-{tone}"><span class="note-icon">{icon("info", 18)}</span><div><strong>{_esc(label)}</strong><span>{_esc(text)}</span></div></div>', unsafe_allow_html=True)


def scope_chips(items: list[tuple[str, str]]) -> None:
    chips = "".join(f'<span class="scope-chip"><small>{_esc(k)}</small>{_esc(v)}</span>' for k, v in items)
    st.markdown(f'<div class="scope-chips">{chips}</div>', unsafe_allow_html=True)


def content_list(items: list[tuple[str, str, str]]) -> None:
    """Report contents: (icon, title, description)."""
    rows = "".join(f'<li><span class="ci">{icon(sym, 18)}</span><div><strong>{_esc(t)}</strong><small>{_esc(d)}</small></div></li>' for sym, t, d in items)
    st.markdown(f'<ul class="content-list">{rows}</ul>', unsafe_allow_html=True)


# --- Data tables -----------------------------------------------------------------

# kind -> (decimals, scale, suffix).  "share" is a 0–1 fraction shown as a percentage.
_TABLE_KINDS = {"int": (0, 1, ""), "pct": (1, 1, " %"), "money": (2, 1, ""), "share": (2, 100, " %")}


def _cell_format(decimals: int, scale: float, suffix: str):
    def fmt(value):
        if value is None or pd.isna(value):
            return "—"
        return number(float(value) * scale, decimals) + suffix
    return fmt


def data_table(frame: pd.DataFrame, columns: dict[str, tuple], *, height: int | str = "auto", key: str | None = None,
               bar: str | None = None) -> None:
    """Sortable table with Ecuadorian figures (127.982 · 55.867.299,38 · 32,0 %) whatever the browser language.

    ``columns`` maps a field to ``(label, kind[, width[, help[, phone label]]])`` with kind text, int, pct, money or
    share.  Values stay numeric, so sorting is exact; the styled text only changes how they read.  Missing values show
    a dash.  ``bar`` names a 0–100 column that gets a label-free bar right after its figure.  Short tables show every
    row.  On phones label columns narrow and headers may use their shorter form.
    """
    order, config, formats = [], {}, {}
    view = frame.copy()
    compact = is_mobile()
    labels = [f for f, spec in columns.items() if f in view and spec[1] == "text"]
    for field, spec in columns.items():
        if field not in view:
            continue
        label, kind, width, help_text, short = (tuple(spec) + (None, None, None))[:5]
        if compact and short:
            label = short
        order.append(field)
        if kind == "text":
            if compact and isinstance(width, int):
                width = max(120, int(width * 0.55))
            # On phones a single label column stays pinned, so the figures scroll sideways and the name stays in view.
            config[field] = st.column_config.TextColumn(label, width=width or "medium", help=help_text,
                                                        pinned=True if compact and len(labels) == 1 else None)
            continue
        view[field] = pd.to_numeric(view[field], errors="coerce").astype(float)
        formats[field] = _cell_format(*_TABLE_KINDS[kind])
        config[field] = st.column_config.NumberColumn(label, width=width, help=help_text)
        if field == bar:
            meter = f"{field}_barra"
            view[meter] = view[field].clip(lower=0, upper=100)
            order.append(meter)
            config[meter] = st.column_config.ProgressColumn(" ", min_value=0, max_value=100, format=" ", width="small")
    view = view[order].reset_index(drop=True)
    if height == "auto" and len(view) <= 20:
        height = 35 * (max(1, len(view)) + 1) + 3
    st.dataframe(view.style.format(formats), hide_index=True, width="stretch", height=height, key=key,
                 placeholder="—", column_config=config)


# --- Report previews -------------------------------------------------------------

def report_preview(kind: str, title: str, period: str, scope: str, kpis: list[tuple[str, str, str]],
                   sheets: list[str], visual: str, slides: tuple[str, str] = ("Resultados por provincia", "Resultados por programa"),
                   pages: int = 1) -> None:
    """Miniature of the product: the summary (``pages`` one or two), the slides or the data workbook.

    ``kpis`` items are (label, value, icon); ``visual`` is the small SVG of the product (map or chart); ``slides``
    names two of the slides after the cover.
    """
    logo = f'<img src="{logo_data()}" alt=""/>' if logo_data() else ""
    tiles = "".join(f'<div><span class="mi">{icon(sym, 13)}</span><strong>{_esc(v)}</strong><span>{_esc(k)}</span></div>'
                    for k, v, sym in kpis[:4])
    if kind == "datos":
        plain = "".join(f'<div><strong>{_esc(v)}</strong><span>{_esc(k)}</span></div>' for k, v, _sym in kpis[:4])
        tabs = "".join(f'<span class="{"on" if i == 0 else ""}">{_esc(s)}</span>' for i, s in enumerate(sheets))
        cols = "".join(f"<i>{c}</i>" for c in "ABCDEFGHIJ")
        body = (f'<div class="xl-window"><div class="xl-chrome"><span class="dots"><i></i><i></i><i></i></span><span class="file">{_esc(title)}</span><span class="ext">XLSX</span></div>'
                f'<div class="xl-formula"><span>A1</span><em>fx</em><b>{_esc(title)}</b></div><div class="xl-cols"><span></span>{cols}</div>'
                f'<div class="xl-sheet"><div class="xl-band">{logo}<div class="xl-title"><small>Libro de datos</small><strong>{_esc(title)}</strong><span>{_esc(period)} · {_esc(scope)}</span></div>{visual}</div>'
                f'<div class="xl-rule"></div><div class="xl-kpis">{plain}</div><div class="xl-rows"><i></i><i></i><i></i><i></i></div></div>'
                f'<div class="xl-tabs">{tabs}</div></div>')
    elif kind == "presentacion":
        bars = "".join(f'<i style="--w:{w}%"></i>' for w in (92, 70, 54, 41, 30))
        body = (f'<div class="deck"><div class="slide-mock"><div class="slide-left">{logo}<small>{_esc(period)}</small><strong>{_esc(title)}</strong>'
                f'<span>{_esc(scope)}</span></div><div class="slide-right"><div class="slide-kpis">{tiles}</div></div></div>'
                f'<div class="deck-row"><div class="mini-slide"><b>{_esc(slides[0])}</b><div class="ms-body">{visual}<div class="ms-bars">{bars}</div></div></div>'
                f'<div class="mini-slide"><b>{_esc(slides[1])}</b><div class="ms-body"><div class="ms-bars">{bars}</div>'
                f'<div class="ms-notes"><i>{icon("award", 11)}</i><i>{icon("pin", 11)}</i><i>{icon("trending-up", 11)}</i></div></div></div></div></div>')
    else:
        bars = "".join(f'<i style="--w:{w}%"></i>' for w in (94, 66, 52, 38, 27, 18))
        notes = "".join(f'<li><span class="mi">{icon(sym, 12)}</span><i></i></li>' for sym in ("award", "pin", "trending-up"))
        body = (f'<div class="page-mock"><div class="page-band">{logo}<div><small>Resumen ejecutivo</small><strong>{_esc(title)}</strong>'
                f'<span>{_esc(period)} · {_esc(scope)}</span></div></div><div class="page-rule"></div><div class="page-body">'
                f'<div class="page-kpis">{tiles}</div><div class="page-map">{visual}<div class="ms-bars">{bars}</div></div>'
                f'<div class="page-foot"><div class="ms-bars">{bars}</div><ul class="page-notes">{notes}</ul></div></div></div>')
        body = f'<div class="page-stack{" two" if pages > 1 else ""}">{body}</div>'
    st.markdown(f'<div class="preview preview-{_esc(kind)}">{body}</div>', unsafe_allow_html=True)


def footer(period: str) -> None:
    logo = f'<img src="{logo_data()}" alt="Gobierno del Ecuador · Ministerio de Trabajo y Desarrollo Humano"/>' if logo_data() else ""
    st.markdown(
        f'<footer class="app-footer"><div class="foot-brand">{logo}</div><div class="foot-meta"><strong>{PRODUCT} · Indicadores estratégicos</strong>'
        f'<span>Fuente: Ministerio de Trabajo y Desarrollo Humano</span><span>Periodo: {_esc(period)}</span></div></footer>',
        unsafe_allow_html=True,
    )
