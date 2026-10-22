"""Extractor público SUT/Power BI y noticia oficial, sin credenciales ni APIs privadas."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .laboral import month, month_end, parse_monthly, parse_retirement_html, validate_snapshot

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "fuentes_laborales.json"


def _official(url: str, hosts: set[str]) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password:
        raise ValueError(f"URL fuera de las fuentes oficiales permitidas: {url}")
    return url


def _download(url: str) -> bytes:
    import requests
    try:
        response = requests.get(url, timeout=(15, 60), headers={"User-Agent": "InfoReportes-MTDH/1.0 public-statistics"})
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"No se pudo consultar la fuente oficial {url}: {exc}") from exc
    _official(response.url, {"sut.trabajo.gob.ec", "www.trabajo.gob.ec", "trabajo.gob.ec"})
    if len(response.content) > 10_000_000:
        raise ValueError("Respuesta HTML demasiado grande; revise la fuente.")
    return response.content


def read_snapshot(page, *, monthly: bool = False) -> dict:
    """Only rendered DOM values: accessible labels and exact SVG chart values."""
    card = page.get_by_role("img", name=re.compile(r"^Cantidad de Contratos [\d.]+\.$"))
    updated = page.get_by_role("img", name=re.compile(r"^Última fecha: fecha_consulta "))
    state = page.get_by_role("listbox", name="Estado contrato", exact=True)
    result = {
        "tarjeta": card.get_attribute("aria-label"),
        "actualizacion": updated.get_attribute("aria-label").removeprefix("Última fecha: fecha_consulta ").removesuffix("."),
        "desde": page.get_by_role("textbox", name=re.compile(r"^Fecha de inicio\.")).input_value(),
        "hasta": page.get_by_role("textbox", name=re.compile(r"^Fecha de finalización\.")).input_value(),
        "estado": dict(state.get_by_role("option").evaluate_all(
            "es => es.map(e => [e.getAttribute('aria-label'), e.getAttribute('aria-checked') === 'true'])")),
        "otros_seleccionados": page.locator('[role="listbox"] [role="option"][aria-checked="true"]').evaluate_all(
            "es => es.filter(e => e.getAttribute('aria-label') !== 'Vigente').map(e => e.getAttribute('aria-label'))"),
        "desplegables": page.get_by_role("combobox").all_text_contents(),
    }
    if monthly:
        chart = page.get_by_role("group", name="Evolución mensual y acumulada de contratos", exact=True)
        axes = chart.get_by_role("listbox", name="Mes", exact=True)
        if axes.count() != 2:
            raise ValueError("Cambió la estructura del eje mensual del SUT.")
        read_labels = "es => es.map(e => e.querySelector('title')?.textContent || e.getAttribute('aria-label') || e.textContent)"
        result["meses"] = axes.nth(0).get_by_role("option").evaluate_all(read_labels)
        result["anios"] = axes.nth(1).get_by_role("option").evaluate_all(read_labels)
        result["valores"] = chart.get_by_role("listbox", name="Cantidad de Contratos", exact=True).get_by_role("option").evaluate_all(
            "es => es.map(e => e.getAttribute('aria-label'))")
    return result


def _stable_snapshot(page, validator, *, monthly=False, timeout=60):
    """Wait for two matching, validated reads, including month sums and filter values."""
    deadline = time.monotonic() + timeout
    previous = None
    last_error = "El tablero sigue cargando."
    while time.monotonic() < deadline:
        try:
            snapshot = read_snapshot(page, monthly=monthly)
            validator(snapshot)
            if snapshot == previous:
                return snapshot
            previous = snapshot
        except (ValueError, AttributeError, KeyError) as exc:
            previous = None
            last_error = str(exc)
        page.wait_for_timeout(1000)
    raise RuntimeError(f"No se obtuvo una lectura estable y validada del SUT: {last_error}")


def collect_laboral(desde: str, hasta: str, *, config: str | Path = DEFAULT_CONFIG, headed=False,
                    launch_options: dict | None = None) -> dict:
    """Fetch a current stock plus complete monthly cohorts, querying one year at a time.

    launch_options allows an organization's managed browser/proxy configuration.
    TLS verification remains enabled. No stored user profile is loaded.
    """
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
        from lxml import html
        import requests  # noqa: F401 - dependency check before opening a browser
    except ImportError as exc:
        raise RuntimeError("Instale requirements-scraping.txt y ejecute python -m playwright install chromium.") from exc
    start, end = month(desde), month_end(month(hasta))
    if start > end:
        raise ValueError("El inicio laboral no puede ser posterior al final.")
    cfg = json.loads(Path(config).read_text(encoding="utf-8"))
    sut_url = _official(cfg["sut_url"], {"sut.trabajo.gob.ec"})
    retirement_url = _official(cfg["jubilados_url"], {"www.trabajo.gob.ec", "trabajo.gob.ec"})
    landing = _download(sut_url)
    frames = html.fromstring(landing).xpath("//iframe[@title=$title]/@src", title=cfg["sut_iframe_title"])
    if len(frames) != 1:
        raise ValueError("No se encontró el iframe oficial del SUT. Revise config/fuentes_laborales.json.")
    powerbi_url = _official(frames[0], {"app.powerbi.com"})
    article = _download(retirement_url)
    retirement = {**parse_retirement_html(article), "url": retirement_url}
    queries = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**{"headless": not headed, **(launch_options or {})})
            try:
                page = browser.new_page(locale="es-EC", viewport={"width": 1920, "height": 1080})
                page.set_default_timeout(15000)
                page.goto(powerbi_url, wait_until="domcontentloaded", timeout=90000)
                page.get_by_role("img", name=re.compile(r"^Cantidad de Contratos [\d.]+\.$")).wait_for(timeout=90000)
                page.get_by_role("textbox", name=re.compile(r"^Fecha de inicio\.")).wait_for(timeout=30000)
                stock = _stable_snapshot(page, validate_snapshot)
                available_start = datetime.strptime(stock["desde"], "%d/%m/%Y").date()
                available_end = datetime.strptime(stock["hasta"], "%d/%m/%Y").date()
                if start < available_start or end > available_end:
                    raise ValueError(f"Pida meses completos dentro de {available_start} a {available_end}; el tablero no cubre el intervalo solicitado.")
                page.get_by_role("button", name="Página siguiente", exact=True).click()
                page.get_by_role("heading", name="Evolución mensual y acumulada de contratos", exact=True).wait_for(timeout=30000)
                for year in range(start.year, end.year + 1):
                    left, right = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
                    # Expand the end before moving start into the next year.
                    for role, value in [(r"^Fecha de finalización\.", right), (r"^Fecha de inicio\.", left)]:
                        field = page.get_by_role("textbox", name=re.compile(role))
                        field.fill(value.strftime("%d/%m/%Y"))
                        field.press("Tab")
                    snap = _stable_snapshot(page, lambda s: parse_monthly(s, left, right), monthly=True)
                    queries.append({"inicio": left.isoformat(), "fin": right.isoformat(), "snapshot": snap})
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise RuntimeError("Falló la lectura del tablero público. Compruebe la conexión, Chromium y los selectores. "
                           "Las bases anteriores se conservan. Detalle: " + str(exc)) from exc
    return {"schema_version": "1.0.0", "metodo": "scraping_dom_publico_y_html_oficial",
            "fecha_consulta_utc": datetime.now(timezone.utc).isoformat(), "desde": desde, "hasta": hasta,
            "sut": {"landing_url": sut_url, "powerbi_url": powerbi_url,
                    "landing_sha256": hashlib.sha256(landing).hexdigest(), "total": stock, "series": queries},
            "jubilados": retirement}
