"""Cargador interno de ENOS. Arranque: streamlit run herramientas/ENOS_Cargador.py

No está integrado al dashboard de producción. Solicita un token de GitHub
solo para la sesión, con permiso Contents: Read and write sobre este repositorio.
Las plantillas validadas se publican como fuentes Excel en GitHub.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ingesta_enos_automatica as engine
from scripts import ingesta_enos_excel as excel_engine
from src.enos_excel import FILES as EXCEL_FILES

REPO = "JuanAmbuludi/Sistema-Reporte-MTDH"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}"
ZONE = ZoneInfo("America/Guayaquil")
DATA_DIR = "data/processed"
PARQUET_DIR = "data/processed/enos_internal"


def github(method, url, token, **kwargs):
    response = requests.request(
        method, url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }, timeout=90, **kwargs)
    if not response.ok:
        raise RuntimeError(f"GitHub HTTP {response.status_code}: {response.text[:400]}")
    return response.json()


def tree(token):
    head = github("GET", f"{API}/git/ref/heads/{BRANCH}", token)["object"]["sha"]
    commit = github("GET", f"{API}/git/commits/{head}", token)
    root = commit["tree"]["sha"]
    paths = github("GET", f"{API}/git/trees/{root}?recursive=1", token)
    if paths.get("truncated"):
        raise RuntimeError("El árbol de GitHub está truncado. Se cancela la publicación.")
    return head, root, {entry["path"]: entry for entry in paths["tree"]}


def read_blob(path, index, token):
    entry = index[path]
    if entry["type"] != "blob":
        raise ValueError("No es archivo: " + path)
    import base64
    item = github("GET", f"{API}/git/blobs/{entry['sha']}", token)
    if item["encoding"] != "base64":
        raise RuntimeError("Codificación no admitida para " + path)
    return base64.b64decode(item["content"])


def publication_paths(index, prefix):
    import re
    pattern = re.compile(r"^data/processed/" + re.escape(prefix) + r"_(\d{4}-\d{2}-\d{2})\.json$")
    return sorted((match.group(1), path) for path in index if (match := pattern.fullmatch(path)))


def last_publication(token, index):
    a, b = publication_paths(index, "seguimiento_enos"), publication_paths(index, "continuidad_servicios")
    if not a or not b:
        raise ValueError("No hay bases históricas suficientes para ENOS.")
    return (a[-1][0], a[-1][1], json.loads(read_blob(a[-1][1], index, token)),
            b[-1][0], b[-1][1], json.loads(read_blob(b[-1][1], index, token)))


def fingerprint(binary):
    return hashlib.sha256(binary).hexdigest()


def prepare(token, inputs, publication, units_date):
    head, root, index = tree(token)
    latest, old_follow_path, snapshot, cont_day, old_cont_path, continuity = last_publication(token, index)
    excel_paths = {kind: f'{excel_engine.FOLDER}/{name}' for kind, name in EXCEL_FILES.items()}
    if any(path in index for path in excel_paths.values()):
        if not all(path in index for path in excel_paths.values()):
            raise ValueError('La base Excel de GitHub está incompleta; restaure las cuatro plantillas.')
        current = {kind: read_blob(path, index, token) for kind, path in excel_paths.items()}
        changes, result = excel_engine.build(snapshot, continuity, current, inputs)
        return {'changed': bool(changes), 'changes': changes, 'result': result, 'head': head,
                'root': root, 'base_day': latest, 'published': result['auditoria']['hasta'],
                'paths': list(changes), 'bytes': sum(len(x) for x in changes.values())}
    if cont_day != latest:
        raise ValueError("Los dos archivos ENOS tienen cortes de publicación distintos. Revisar antes de actualizar.")
    if publication < latest:
        raise ValueError(f"El reporte {publication} es anterior al último publicado ({latest}).")
    ledger_path = f"{DATA_DIR}/cortes_riesgos.json"
    ledger = json.loads(read_blob(ledger_path, index, token))
    if publication in ledger.get("cerrados", {}):
        raise ValueError("Esta publicación está cerrada; no se puede sobrescribir.")
    if publication == latest:
        day_paths = (old_follow_path, old_cont_path)
    else:
        day_paths = (f"{DATA_DIR}/seguimiento_enos_{publication}.json",
                     f"{DATA_DIR}/continuidad_servicios_{publication}.json")
        if any(path in index for path in day_paths):
            raise ValueError("Conflicto: existe parcialmente un corte para este día.")
    outputs, result = engine.build(snapshot, continuity, inputs, publication, units_date)
    if not outputs:
        return {"changed": False, "result": result}
    changes = {
        day_paths[0]: outputs["seguimiento"],
        day_paths[1]: outputs["continuidad"],
        f"{PARQUET_DIR}/alertas.parquet": outputs["parquet_alertas"],
        f"{PARQUET_DIR}/kits.parquet": outputs["parquet_kits"],
        f"{PARQUET_DIR}/unidades_suspendidas.parquet": outputs["parquet_unidades"],
    }
    if publication > latest:
        ledger.setdefault("cerrados", {}).setdefault(latest, {}).update({
            Path(old_follow_path).name: fingerprint(read_blob(old_follow_path, index, token)),
            Path(old_cont_path).name: fingerprint(read_blob(old_cont_path, index, token)),
        })
        changes[ledger_path] = (json.dumps(ledger, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # Exige coincidencia estricta de esquemas contractuales; permite extensión
    # únicamente dentro de arreglos que admiten campos opcionales.
    updated = json.loads(outputs["seguimiento"])
    original = snapshot
    if set(updated) != set(original):
        raise ValueError("La ingesta alteraría las claves del JSON de seguimiento.")
    new_cont = json.loads(outputs["continuidad"])
    if set(new_cont) != set(continuity):
        raise ValueError("La ingesta alteraría las claves del JSON de continuidad.")
    if len(updated["alertas"]) != len({row["codigo"] for row in updated["alertas"]}):
        raise ValueError("Códigos de alerta repetidos después de conciliar.")
    if len(updated["kits"]) != len({row["id_kobo"] for row in updated["kits"]}):
        raise ValueError("IDs Kobo repetidos después de conciliar.")
    return {"changed": True, "changes": changes, "result": result, "head": head,
            "root": root, "base_day": latest, "published": publication,
            "paths": list(changes), "bytes": sum(len(x) for x in changes.values())}


def commit_changes(token, plan):
    """Publicación atómica: un solo commit, nunca un archivo a medio actualizar."""
    import base64
    current = github("GET", f"{API}/git/ref/heads/{BRANCH}", token)["object"]["sha"]
    if current != plan["head"]:
        raise RuntimeError("El repositorio cambió después de la validación. Recargar y revisar nuevamente.")
    entries = []
    for path, binary in plan["changes"].items():
        obj = github("POST", f"{API}/git/blobs", token, json={
            "content": base64.b64encode(binary).decode("ascii"),
            "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": obj["sha"]})
    new_tree = github("POST", f"{API}/git/trees", token, json={
        "base_tree": plan["root"], "tree": entries})["sha"]
    new_commit = github("POST", f"{API}/git/commits", token, json={
        "message": f"ENOS: actualizar fuentes validadas {plan['published']} (cargador interno)",
        "tree": new_tree, "parents": [plan["head"]]})["sha"]
    # Evita perder actualizaciones concurrentes: sin force y refuerza consulta previa.
    current = github("GET", f"{API}/git/ref/heads/{BRANCH}", token)["object"]["sha"]
    if current != plan["head"]:
        raise RuntimeError("La rama cambió durante la publicación. No se modificó main.")
    github("PATCH", f"{API}/git/refs/heads/{BRANCH}", token,
           json={"sha": new_commit, "force": False})
    return f"https://github.com/{REPO}/commit/{new_commit}"


st.set_page_config(page_title="Centro de actualización | ENOS", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown("""<style>
:root {color-scheme: light;}
.block-container {max-width:1190px; padding-top:2.15rem; padding-bottom:3rem;}
h1,h2,h3 {letter-spacing:-.025em;}
[data-testid="stSidebar"] {background: #f3f5f9; border-right:1px solid #e0e5ee;}
[data-testid="stSidebar"] .block-container {padding-top:2.5rem;}
[data-testid="stFileUploader"] {border:1px dashed #a5b4c7; border-radius:16px;}
[data-testid="stMetric"] {background:#f7f8fb;border:1px solid #e3e8ef;border-radius:14px;padding:15px 18px;}
div.stButton button[kind="primary"] {background:#183052; border-radius:10px;border:1px solid #183052;}
div.stButton button {border-radius:10px;}
.enos-eyebrow {font-size:.81rem;font-weight:700;color:#58708f;letter-spacing:.12em;text-transform:uppercase;}
.enos-lead {color:#52637c;font-size:1.04rem;margin:-.2rem 0 1.4rem;}
.enos-block {border:1px solid #dde5ef; border-radius:14px; padding:16px 20px; background:#fff;}
.enos-pill {display:inline-block; background:#edf1f6; color:#27425d; padding:5px 12px;border-radius:100px;font-size:.79rem;margin-right:8px;}
</style>""", unsafe_allow_html=True)
st.markdown('<div class="enos-eyebrow">MTDH · Monitoreo institucional</div>', unsafe_allow_html=True)
st.title("Centro de actualización ENOS")
st.markdown('<div class="enos-lead">Importación, conciliación y publicación controlada de fuentes operativas.</div>',
            unsafe_allow_html=True)
st.markdown('<span class="enos-pill">Herramienta interna independiente</span>'
            '<span class="enos-pill">Bases Excel editables</span>'
            '<span class="enos-pill">Histórico protegido</span>', unsafe_allow_html=True)
st.write("")
st.info("Revise las cifras antes de publicar. Los datos actualizan las consultas del tablero y sus exportaciones; el diseño y los reportes publicados se conservan.")

with st.sidebar:
    st.markdown("### Configuración")
    st.caption("Autorización y fechas de la carga.")
    token = st.text_input("Token personal con permiso Contents: Read and write", type="password",
                          help="Permiso exclusivamente para el repositorio Sistema-Reporte-MTDH.")
    now = datetime.now(ZONE).date()
    report_date = unit_cut = now
    st.caption("Las fechas se toman de Control y de las filas de cada Excel.")
    st.caption("El token no se publica en GitHub. No adjunte información personal sin autorización institucional.")
    st.divider()
    st.caption("Repositorio: JuanAmbuludi / Sistema-Reporte-MTDH")
    st.caption("Destino: main · archivos de datos únicamente")

st.markdown("### 1 · Importar fuentes")
st.caption("Cargue uno o varios de los cuatro Excel editables. Descargue primero la versión vigente de data/enos_excel.")
st.markdown(f"[Descargar bases e instrucciones](https://github.com/{REPO}/tree/{BRANCH}/data/enos_excel)")
uploads = st.file_uploader("Archivos Excel (.xlsx)", type=["xlsx"], accept_multiple_files=True,
                           help="Plantillas con hojas Datos y Control: alertas, kits, unidades suspendidas y contingencias.")

files = {}
errors = []
for upload in uploads or []:
    try:
        binary = upload.getvalue()
        kind = engine.classify(binary)
        if kind == "desconocido":
            raise ValueError("Formato no reconocido; no se publicará sin validar.")
        if kind in files:
            raise ValueError(f"Ya hay un archivo de {kind}. Envíe solo uno por tipo.")
        files[kind] = (upload.name, binary)
    except Exception as exc:
        errors.append(f"{upload.name}: {exc}")
if files:
    for label, item in files.items():
        st.markdown(f"**{label.capitalize()}** · `{item[0]}`")
for err in errors:
    st.error(err)

if "enos_plan" not in st.session_state:
    st.session_state.enos_plan = None
if "enos_signature" not in st.session_state:
    st.session_state.enos_signature = None

signature = (report_date.isoformat(), unit_cut.isoformat(),
             tuple(sorted((k, hashlib.sha256(b).hexdigest()) for k, (_, b) in files.items())))

st.markdown("### 2 · Conciliar y validar")
st.caption("No se escribe nada en GitHub durante esta etapa.")
if st.button("Validar archivos y comparar con GitHub", disabled=not token or not files or bool(errors), type="primary"):
    try:
        with st.spinner("Conciliando todas las fuentes con GitHub..."):
            plan = prepare(token, files, report_date.isoformat(), unit_cut.isoformat())
        st.session_state.enos_plan = plan
        st.session_state.enos_signature = signature
        if not plan["changed"]:
            st.info("Los archivos ya fueron procesados. No hay cambios por publicar.")
        else:
            st.success("Validaciones superadas. Revise el detalle antes de publicar.")
    except Exception as exc:
        st.session_state.enos_plan = None
        st.error(f"Publicación bloqueada: {exc}")

plan = st.session_state.enos_plan
if plan and st.session_state.enos_signature == signature:
    st.markdown("### 3 · Resultado de la auditoría")
    report = plan["result"].get("auditoria", {})
    if report:
        a,b,c,d = st.columns(4)
        a.metric("Alertas históricas", f'{report["alertas_historico"]:,}')
        b.metric("Alertas del período", f'{report["alertas_periodo_con_criterio"]:,}')
        c.metric("Kits del período", f'{report["kits_periodo"]:,}')
        d.metric("Unidades suspendidas", f'{report["unidades_suspendidas"]:,}')
        st.caption(f'Período consultado: {report["desde"]} a {report["hasta"]} · '
                   f'Corte de unidades: {report.get("corte_unidades") or "No disponible"}')
        st.markdown("#### Conciliación de variaciones")
        c1,c2,c3 = st.columns(3)
        c1.metric("Nuevos códigos de alerta", report["nuevos_codigos_historico"])
        c2.metric("Nuevos ID Kobo", report["nuevos_ids_kobo"])
        c3.metric("Kits históricos", f'{report["kits_historico"]:,}')
        if report.get("coincidencias_ua_fecha"):
            st.warning(f'Hay {len(report["coincidencias_ua_fecha"])} coincidencias de UA y fecha '
                       'entre códigos de alerta. No se han fusionado; deben revisarse.')
            st.dataframe(report["coincidencias_ua_fecha"], use_container_width=True, hide_index=True)
        if (not report["bonos_sin_modificar"] and not report.get('contingencias_autorizadas')) or not report["brigadas_sin_modificar"]:
            st.error("Se detectaron cambios fuera del alcance. Publicación no permitida.")
        else:
            st.success("Las cifras corresponden a las fuentes seleccionadas.")
        if report.get('formato_excel'):
            a,b,c,d = st.columns(4)
            a.metric('Núcleos habilitados', report['nucleos_habilitados'])
            b.metric('Monto habilitado', f"USD {report['monto_habilitado']:,.2f}")
            c.metric('Núcleos cobrados', report['nucleos_cobrados'])
            d.metric('Monto cobrado', f"USD {report['monto_cobrado']:,.2f}")
    else:
        st.info("No hay nueva auditoría: el archivo ya se había procesado.")
    with st.expander("Detalle técnico de conciliación y fuentes", expanded=False):
        st.json(plan["result"])
    if plan["changed"]:
        st.caption(f"Archivos a actualizar: {len(plan['paths'])}. No se modificarán archivos del dashboard.")
        st.code("\n".join(plan["paths"]), language="text")
        st.markdown("### 4 · Publicación controlada")
        st.info("Esta operación publicará solo archivos de datos ENOS en GitHub. "
                "Actualiza las cifras de las consultas actuales y conserva los documentos ya publicados.")
        agree = st.checkbox("Revisé las cifras, las alertas potencialmente coincidentes, las fuentes y sus cortes.")
        if st.button("Publicar datos validados en GitHub", disabled=not agree or not token, type="primary"):
            try:
                with st.spinner("Creando un único commit validado..."):
                    link = commit_changes(token, plan)
                st.success("Datos publicados correctamente.")
                st.markdown(f"[Ver commit publicado en GitHub]({link})")
                st.session_state.enos_plan = None
            except Exception as exc:
                st.error(f"No se publicó: {exc}")
elif plan:
    st.warning("Cambió algún archivo o fecha. Valide nuevamente antes de publicar.")
