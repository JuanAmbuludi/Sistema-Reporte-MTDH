"""Tabla 4: esquema, validación y persistencia de agregados laborales públicos.

Las fechas de consulta, actualización de fuente y referencia estadística son
dimensiones distintas. Ningún dato de jubilaciones se imputa a septiembre.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from lxml import html
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "1.0.0"
MONTHS = "ene feb mar abr may jun jul ago sep oct nov dic".split()
SCHEMA = pa.schema([
    pa.field("consulta_id", pa.string(), nullable=False),
    pa.field("indicador_id", pa.string(), nullable=False),
    pa.field("indicador", pa.string(), nullable=False),
    pa.field("territorio", pa.string(), nullable=False),
    pa.field("periodo", pa.date32()),
    pa.field("anio", pa.int16()),
    pa.field("granularidad", pa.string(), nullable=False),
    pa.field("naturaleza", pa.string(), nullable=False),
    pa.field("valor", pa.decimal128(24, 2), nullable=False),
    pa.field("operador", pa.string(), nullable=False),
    pa.field("unidad", pa.string(), nullable=False),
    pa.field("filtro_desde", pa.date32()),
    pa.field("filtro_hasta", pa.date32()),
    pa.field("fecha_consulta_utc", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("actualizacion_fuente", pa.string()),
    pa.field("publicacion_fuente", pa.string()),
    pa.field("fuente_url", pa.string(), nullable=False),
    pa.field("fuente_id", pa.string(), nullable=False),
    pa.field("evidencia_sha256", pa.string(), nullable=False),
    pa.field("filtros_json", pa.string(), nullable=False),
    pa.field("nota", pa.string(), nullable=False),
], metadata={b"mtdh.schema_version": SCHEMA_VERSION.encode(),
             b"mtdh.grain": b"consulta_id/indicador_id/periodo/territorio",
             b"mtdh.warning": b"Read operador and naturaleza before aggregation."})


def month(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("El mes laboral debe tener formato AAAA-MM.")
    return date.fromisoformat(value + "-01")


def month_end(value: date) -> date:
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def integer(text: str) -> int:
    """Accept exact Spanish counts, never rounded chart labels like '52,1 mil'."""
    if not isinstance(text, str) or not re.fullmatch(r"(?:\d+|\d{1,3}(?:\.\d{3})+)", text.strip()):
        raise ValueError(f"Conteo exacto no reconocido: {text!r}")
    return int(text.strip().replace(".", ""))


def card_count(label: str) -> int:
    match = re.fullmatch(r"Cantidad de Contratos ([\d.]+)\.", label)
    if not match:
        raise ValueError("Cambió la tarjeta Cantidad de Contratos del SUT.")
    return integer(match[1])


def validate_snapshot(snapshot: dict) -> int:
    if snapshot.get("estado") != {"Finalizado": False, "Vigente": True}:
        raise ValueError("El tablero debe tener únicamente Estado contrato = Vigente.")
    # Other list slicers must have no active selection; dropdowns must be all.
    if any(snapshot.get("otros_seleccionados", [])):
        raise ValueError("Hay filtros adicionales seleccionados en el SUT.")
    if any(not re.match(r"^(Todas|Todos)\b", x) for x in snapshot.get("desplegables", [])):
        raise ValueError("El tablero no está mostrando el universo nacional completo.")
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{1,2}:\d{2}:\d{2}", snapshot.get("actualizacion", "")):
        raise ValueError("Falta la fecha de actualización de la fuente SUT.")
    start = datetime.strptime(snapshot["desde"], "%d/%m/%Y").date()
    end = datetime.strptime(snapshot["hasta"], "%d/%m/%Y").date()
    if start > end:
        raise ValueError("El intervalo visible del SUT está invertido.")
    return card_count(snapshot["tarjeta"])


def parse_monthly(snapshot: dict, start: date, end: date) -> list[tuple[date, int]]:
    if start.year != end.year:
        raise ValueError("Cada consulta mensual al tablero debe abarcar un solo año.")
    total = validate_snapshot(snapshot)
    if snapshot["desde"] != start.strftime("%d/%m/%Y") or snapshot["hasta"] != end.strftime("%d/%m/%Y"):
        raise ValueError("El filtro de fechas visible no coincide con el solicitado.")
    if snapshot.get("anios") != [str(start.year)]:
        raise ValueError("El eje del gráfico no identifica el año solicitado.")
    expected = MONTHS[start.month - 1:end.month]
    if snapshot.get("meses") != expected or len(snapshot.get("valores", [])) != len(expected):
        raise ValueError("Serie mensual incompleta o eje de meses inesperado; no se rellenan ceros.")
    values = [integer(v) for v in snapshot["valores"]]
    if sum(values) != total:
        raise ValueError("La suma mensual no coincide con la tarjeta del período filtrado.")
    return [(date(start.year, start.month + i, 1), v) for i, v in enumerate(values)]


def parse_retirement_html(content: bytes) -> dict:
    root = html.fromstring(content, parser=html.HTMLParser(encoding="utf-8"))
    paragraphs = [" ".join(p.text_content().split()) for p in root.xpath("//p")]
    candidates = [p for p in paragraphs if re.search(r"Solo durante\s+\d{4}", p, re.I)]
    if len(candidates) != 1:
        raise ValueError("No se encontró un único balance anual de compensaciones jubilares.")
    text = candidates[0]
    match = re.fullmatch(
        r"Solo durante (\d{4}), el Gobierno Nacional ha destinado (más de )?USD ((?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?) millones "
        r"para el pago de compensaciones jubilares, beneficiando a ([\d.]+) exservidores y extrabajadores\.",
        text, re.I)
    if not match:
        raise ValueError("Cambió la redacción de la fuente de jubilados; revise el extractor.")
    amount = Decimal(match[3].replace(".", "").replace(",", ".")) * Decimal(1_000_000)
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Monto de jubilaciones inválido.")
    published = root.xpath('//meta[@property="article:published_time"]/@content')
    return {"anio": int(match[1]), "beneficiarios": integer(match[4]),
            "monto_usd": str(amount), "operador_monto": ">" if match[2] else "=",
            "parrafo": text, "publicacion": published[0] if published else None,
            "html_sha256": hashlib.sha256(content).hexdigest()}


def build_laboral(evidence: dict, output: str | Path) -> dict:
    """Validate all sources before writing; caller stages output before publication."""
    collected = datetime.fromisoformat(evidence["fecha_consulta_utc"])
    if collected.utcoffset() is None:
        raise ValueError("La fecha de consulta debe indicar su zona horaria.")
    collected = collected.astimezone(timezone.utc)
    raw = json.dumps(evidence, ensure_ascii=False, indent=2).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    run_id = collected.strftime("%Y%m%dT%H%M%S%fZ") + "_" + digest[:8]
    sut = evidence["sut"]
    stock = sut["total"]
    total = validate_snapshot(stock)
    jubilados = evidence["jubilados"]
    # Reparse retained source excerpt; never trust supplied derived numbers alone.
    from html import escape
    parsed = parse_retirement_html(("<p>" + escape(jubilados["parrafo"]) + "</p>").encode())
    for field in ["anio", "beneficiarios", "monto_usd", "operador_monto"]:
        if parsed[field] != jubilados[field]:
            raise ValueError(f"La evidencia de jubilados no concilia: {field}.")
    common = {"consulta_id": run_id, "territorio": "Ecuador", "periodo": None, "anio": None,
              "fecha_consulta_utc": collected, "evidencia_sha256": digest,
              "actualizacion_fuente": None, "publicacion_fuente": None,
              "filtro_desde": None, "filtro_hasta": None}
    rows = []

    def add(identifier, label, value, unit, grain, nature, operator, source_id, url, filters, note, **extra):
        rows.append({**common, "indicador_id": identifier, "indicador": label,
                     "valor": Decimal(str(value)).quantize(Decimal("0.01")), "unidad": unit,
                     "granularidad": grain, "naturaleza": nature, "operador": operator,
                     "fuente_id": source_id, "fuente_url": url,
                     "filtros_json": json.dumps(filters, ensure_ascii=False, sort_keys=True),
                     "nota": note, **extra})

    add("contratos_vigentes_total", "Contratos vigentes: total del tablero", total, "contratos",
        "consulta", "stock_consultado", "=", "sut_contratos", sut["powerbi_url"],
        {"estado": "Vigente", "ambito": "nacional", "desde": stock["desde"], "hasta": stock["hasta"]},
        "Total del tablero a la actualización indicada; no equivale a un cierre histórico de septiembre. "
        "Contratos, no personas únicas. El intervalo corresponde al filtro visible de la fuente.",
        actualizacion_fuente=stock["actualizacion"],
        filtro_desde=datetime.strptime(stock["desde"], "%d/%m/%Y").date(),
        filtro_hasta=datetime.strptime(stock["hasta"], "%d/%m/%Y").date())
    months_seen = set()
    for query in sut["series"]:
        start, end = date.fromisoformat(query["inicio"]), date.fromisoformat(query["fin"])
        snap = query["snapshot"]
        if snap["actualizacion"] != stock["actualizacion"]:
            raise ValueError("El SUT se actualizó durante la extracción; vuelva a consultar.")
        for period, value in parse_monthly(snap, start, end):
            if period in months_seen:
                raise ValueError("Hay meses duplicados en la extracción.")
            months_seen.add(period)
            add("contratos_del_mes_vigentes", "Contratos del mes con estado vigente al consultar",
                value, "contratos", "mensual", "cohorte_con_estado_actual", "=",
                "sut_contratos", sut["powerbi_url"],
                {"estado": "Vigente", "ambito": "nacional", "desde": snap["desde"], "hasta": snap["hasta"]},
                "Mes según el filtro y eje del SUT. Registros transaccionales: se pueden revisar. "
                "No es el stock de vigentes al cierre de cada mes ni el total de nuevas contrataciones "
                "de todos los estados. No sumar a contratos_vigentes_total.",
                periodo=period, anio=period.year, actualizacion_fuente=snap["actualizacion"],
                filtro_desde=start, filtro_hasta=end)
    requested_start, requested_end = month(evidence["desde"]), month(evidence["hasta"])
    expected = {date(y, m, 1) for y in range(requested_start.year, requested_end.year + 1)
                for m in range(1, 13) if requested_start <= date(y, m, 1) <= requested_end}
    if not expected or months_seen != expected:
        raise ValueError("La extracción no cubre todos los meses solicitados.")
    if sum(r["valor"] for r in rows if r["indicador_id"] == "contratos_del_mes_vigentes") > total:
        raise ValueError("Las cohortes mensuales exceden el total de contratos vigentes.")
    note = ("Balance anual publicado; la frase anual no documenta el día ni el mes de cierre. "
            "La fecha de publicación y la de consulta no son el corte estadístico. "
            "Esta noticia configurada no constituye una serie mensual ni se actualiza automáticamente a noticias nuevas.")
    for identifier, label, value, unit, operator in [
        ("jubilados_compensados", "Exservidores y extrabajadores compensados", jubilados["beneficiarios"], "personas", "="),
        ("compensaciones_jubilares_usd", "Recursos para compensaciones jubilares", jubilados["monto_usd"], "USD", jubilados["operador_monto"]),
    ]:
        add(identifier, label, value, unit, "anual_corte_no_documentado", "acumulado_anual_publicado",
            operator, "mdt_noticia_jubilados", jubilados["url"], {"anio": jubilados["anio"]},
            note + (" El operador > significa límite inferior, no monto exacto." if operator == ">" else ""),
            anio=jubilados["anio"], publicacion_fuente=jubilados.get("publicacion"))
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence_path = Path("laboral_evidencias") / (run_id + ".json")
    archive_path = Path("laboral_cortes") / (run_id + ".parquet")
    for rel in [evidence_path, archive_path]:
        (output / rel).parent.mkdir(parents=True, exist_ok=True)
    (output / evidence_path).write_bytes(raw)
    pq.write_table(table, output / "gestion_laboral.parquet", compression="zstd")
    (output / archive_path).write_bytes((output / "gestion_laboral.parquet").read_bytes())
    with (output / "gestion_laboral.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCHEMA.names)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {"schema_version": SCHEMA_VERSION, "consulta_id": run_id,
                "fecha_consulta_utc": evidence["fecha_consulta_utc"], "filas": len(rows),
                "meses_contratos": sorted(p.strftime("%Y-%m") for p in months_seen),
                "evidencia": str(evidence_path.as_posix()), "evidencia_sha256": digest,
                "copia_del_corte": str(archive_path.as_posix()),
                "parquet_sha256": hashlib.sha256((output / "gestion_laboral.parquet").read_bytes()).hexdigest(),
                "fuentes": {"sut": sut["landing_url"], "powerbi": sut["powerbi_url"], "jubilados": jubilados["url"]},
                "controles": {"meses_completos": True, "sumas_conciliadas": True, "filtro_vigente": True},
                "advertencias": ["No sumar indicadores, unidades, cortes ni naturalezas diferentes.",
                    "Los meses del SUT son cohortes con estado actual, no stocks históricos.",
                    "El monto de jubilaciones respeta el operador de la fuente; > es límite inferior.",
                    "Jubilados: año conocido, mes de cierre no documentado. Noticia configurada, no feed automático.",
                    "No incluye contingencias ni ejecución presupuestaria general."]}
    (output / "manifest_laboral.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
