"""Scrape the published data resources used by both SGDE pages.

No browser or credentials are needed. Parallel tabulations are kept in separate
tables: joining or summing them would multiply contracts. The source publishes
province/canton, but neither parish nor historical contract-start months.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin
import hashlib
import json
import re

import pandas as pd

from .historicos import periods

BASE = "https://sgde-indicadores.github.io/Ministerio-de-Trabajo-y-Desarrollo-Humano/"
PAGES = ["MDTDH/kpi_contratos.html", "MDTDH/kpis.html"]
FILES = ["datos/kpis/contratos/dashboard_data.json", "datos/kpis/kpi_trabajo.csv",
         "datos/kpis/jubilados/corte.csv", "datos/kpis/jubilados/gestion.csv",
         "datos/kpis/jovenes_accion/periodos.csv"]
NAMES = {"estado": "estado", "sexo": "sexo", "edad": "grupo_edad", "disc": "discapacidad",
         "prov": "provincia", "tipo": "tipo_contrato", "etnia": "etnia", "nac": "nacionalidad",
         "rama": "rama_actividad"}


def collect(local=None):
    data, receipts = {}, []
    for path in [*PAGES, *FILES]:
        if local:
            raw = (Path(local)/path).read_bytes()
        else:
            import requests
            response = requests.get(urljoin(BASE, path), timeout=(15, 60),
                                    headers={"User-Agent": "InfoReport-MTDH/2.0 (public aggregate data)"})
            response.raise_for_status()
            raw = response.content
        data[path] = raw.decode("utf-8-sig")
        receipts.append({"url": urljoin(BASE, path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    for page in PAGES:
        if "../datos/kpis/contratos/dashboard_data.json" not in data[page]:
            raise ValueError(f"La página {page} cambió de fuente de contratos.")
    if "../datos/kpis/kpi_trabajo.csv" not in data[PAGES[1]]:
        raise ValueError("No se identifica la fuente de los KPIs laborales.")
    return data, {"consulta_utc": datetime.now(timezone.utc).isoformat(), "recursos": receipts,
                  "metodo": "Extracción de los JSON/CSV públicos enlazados por las páginas HTML"}


def contracts(payload):
    d = json.loads(payload)
    expected = {"base", "canton", "rama", "tipo", "etnia", "nac", "act", "empresas"}
    if d.get("version") != 3 or d.get("naturaleza") != "foto_diaria" or set(d.get("t", {})) != expected:
        raise ValueError("Cambió el contrato de datos de SGDE; no publicar una extracción incompleta.")
    cut = pd.Timestamp(d["fecha_corte"]).date().isoformat()
    outputs = {}
    for name, values in d["t"].items():
        source = pd.DataFrame(values, columns=d["cols"][name])
        if source.duplicated(list(source.columns[:-1])).any() or (source.n < 0).any() or (source.n % 1 != 0).any():
            raise ValueError(f"Claves o conteos de contratos inválidos: {name}")
        out = pd.DataFrame(index=source.index)
        for c in source.columns[:-1]:
            dictionary = d["dic"][c]
            index = source[c]
            if ((index < (-1 if name == "empresas" else 0)) | (index >= len(dictionary))).any():
                raise ValueError(f"Índice de catálogo inválido: {name}/{c}")
            if c == "canton":
                out["provincia"] = index.map(lambda i: d["dic"]["prov"][dictionary[i][0]])
                out["canton"] = index.map(lambda i: dictionary[i][1])
            elif c == "act":
                out["rama_actividad"] = index.map(lambda i: d["dic"]["rama"][dictionary[i][0]])
                out["actividad"] = index.map(lambda i: dictionary[i][1])
            else:
                out[NAMES[c]] = index.map(lambda i: "TOTAL" if i == -1 else dictionary[i])
        out["empresas" if name == "empresas" else "contratos"] = source.n.astype("int32")
        measure = "empresas" if name == "empresas" else "contratos"
        dims = [c for c in out if c != measure]
        # The activity dictionary contains separate indices with identical labels.
        # Decode first, then collapse those labels without losing any contracts.
        if out.duplicated(dims).any():
            if name == "empresas":
                raise ValueError("Empresas distintas no se pueden sumar entre claves duplicadas.")
            out = out.groupby(dims, as_index=False, dropna=False)[measure].sum()
        out["fecha_corte"] = cut
        out["periodo"] = cut[:7]
        outputs[f"contratos_{name}"] = periods(out)
    total = int(outputs["contratos_base"].contratos.sum())
    if total != int(d["registrados"]):
        raise ValueError("Contratos no concilian con el total publicado.")
    base = outputs["contratos_base"].groupby(["estado", "provincia"]).contratos.sum().sort_index()
    for name in ["canton", "rama", "tipo", "etnia", "act"]:
        compare = outputs[f"contratos_{name}"].groupby(["estado", "provincia"]).contratos.sum().sort_index()
        if not base.equals(compare):
            raise ValueError(f"La tabla {name} no concilia por estado y provincia.")
    nationalities = outputs["contratos_nac"].groupby(["estado", "provincia"]).contratos.sum()
    if (nationalities > base.reindex(nationalities.index)).any():
        raise ValueError("Los contratos extranjeros exceden el universo.")
    return outputs, {"fecha_corte": cut, "fecha_hora_corte": d.get("fecha_hora_corte"),
        "registrados": total, "por_estado": outputs["contratos_base"].groupby("estado").contratos.sum().astype(int).to_dict(),
        "territorio": "Provincia y cantón; la fuente no publica parroquia.",
        "naturaleza": "Stock registrado a fecha_corte, no nuevos contratos del mes.",
        "nacionalidad": "Solo contratos de personas extranjeras; no suma al universo completo.",
        "empresas": "Conteos distintos por estado/territorio; TOTAL es un agregado aparte, no sumable con provincias."}


def retirement(data):
    cut = pd.read_csv(StringIO(data[FILES[2]])).iloc[0].corte
    d = pd.read_csv(StringIO(data[FILES[3]]), dtype={"codigo": str})
    d.codigo = d.codigo.fillna("")
    d["fecha_corte"] = str(cut)
    # Complete prior calendar years have no invented monthly observation.
    d["periodo"] = [str(y) if not partial else f"{y}-{m:02d}" for y, m, partial in zip(d.anio, d.mes_fin, d.parcial)]
    d["mes"] = pd.array([m if partial else None for m, partial in zip(d.mes_fin, d.parcial)], dtype="Int8")
    from .historicos import MONTHS
    d["mes_nombre"] = d.mes.map(lambda m: MONTHS[int(m)-1] if pd.notna(m) else None)
    for year, sub in d.groupby("anio"):
        total = sub.loc[sub.dimension.eq("total")]
        if len(total) != 1:
            raise ValueError("Falta el total anual de jubilados.")
        for dimension, block in sub.groupby("dimension"):
            if int(block.expedientes.sum()) != int(total.expedientes.iloc[0]) or abs(block.monto_usd.sum()-total.monto_usd.iloc[0]) > 0.05:
                raise ValueError(f"Jubilados no concilian: {year}/{dimension}")
    return d


def youth(data):
    d = pd.read_csv(StringIO(data[FILES[4]]))
    executed = d.loc[d.estado.isin(["ejecutado", "en_ejecucion"]) & d.corte_ejecucion.notna()]
    latest = executed.loc[executed.orden.idxmax()]
    if int(latest.orden) != 3:
        raise ValueError("Hay una nueva fase de Jóvenes en Acción con ejecución; revise la validación oficial antes de cambiarla.")
    return {"fase": int(latest.orden), "periodo": latest.corte_ejecucion,
            "registrados": int(latest.registrados), "habilitados": int(latest.beneficiarios),
            "presupuesto_publicado": float(latest.presupuesto_usd), "ejecucion_publicada": float(latest.ejecucion_usd)}


def youth_phases(data):
    """Phases of Jóvenes en Acción with documented execution or attention (scheduled phases are left out).

    Every row keeps the figures the public resource publishes for its phase: registered young people, participants
    (enabled or attended), transfers and their amount, budget and execution with its cut.  The snapshot is dated by the
    latest execution cut, so a new publication replaces it.
    """
    from decimal import Decimal
    d = pd.read_csv(StringIO(data[FILES[4]]))
    d = d.loc[d.estado.isin(["ejecutado", "en_ejecucion"])].copy()
    if d.empty:
        raise ValueError("No hay fases de Jóvenes en Acción con ejecución publicada.")
    cut = str(d.corte_ejecucion.dropna().max())
    out = pd.DataFrame({
        "periodo": cut, "fase": d.orden.astype("int8"), "nombre_fase": d.periodo.astype(str), "etiqueta": d.etiqueta.astype(str),
        "estado": d.estado.astype(str), "inicio": d.inicio.astype(str), "fin": d.fin.where(d.fin.notna(), None),
        "registrados": pd.array(d.registrados, dtype="Int64"), "participantes": pd.array(d.beneficiarios, dtype="Int64"),
        "transferencias": pd.array(d.transferencias, dtype="Int16"),
        "monto_transferencia_usd": [None if pd.isna(v) else Decimal(str(v)) for v in d.monto_transferencia_usd],
        "presupuesto_usd": [None if pd.isna(v) else Decimal(str(v)) for v in d.presupuesto_usd],
        "ejecucion_usd": [None if pd.isna(v) else Decimal(str(v)) for v in d.ejecucion_usd],
        "corte_ejecucion": d.corte_ejecucion.where(d.corte_ejecucion.notna(), None), "nota": d.nota.astype(str),
    })
    return periods(out)

