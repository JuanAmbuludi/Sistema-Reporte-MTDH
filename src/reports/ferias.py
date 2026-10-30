"""The two training sources remain separate in every institutional bulletin."""
from __future__ import annotations

from src import corte
from src.data import MONTHS

TITLE = "Ferias de Inclusión Económica, Empleabilidad y Autoempleo"
SOURCE_LABELS = {
    "empleabilidad_autoempleo": "Empleabilidad y autoempleo",
    "inclusion_economica": "Inclusión económica",
}


def period_block(start: str, end: str, span: str, *, yearly: bool = False) -> dict | None:
    from src import ferias
    from .context import number

    data = ferias.load()
    if data.empty:
        return None
    rows = data.loc[data.periodo_id.astype(str).between(start, end)].copy()
    if rows.empty:
        return None
    totals, kpis = [], []
    for source, label in SOURCE_LABELS.items():
        selected = rows.loc[rows.fuente.eq(source)]
        if selected.empty:
            continue
        total = int(selected.participaciones.sum())
        totals.append({"fuente": source, "label": label, "participaciones": total})
        kpis.append({"label": label, "value": total, "kind": "count", "note": "Registros de participación", "icon": "graduation"})
    for item in totals:
        selected = rows.loc[rows.fuente.eq(item["fuente"])]
        provinces = selected.loc[selected.provincia_codigo.fillna("").ne(""), "provincia_codigo"].nunique()
        kpis.append({"label": f"Provincias · {item['label'].lower()}", "value": int(provinces), "kind": "count", "note": "Territorios con registros", "icon": "map"})

    rows["corte"] = rows.periodo_id.str[:4] if yearly else rows.periodo_id
    series = rows.groupby(["corte", "fuente"]).participaciones.sum().unstack("fuente")
    table_rows = []
    for cut, values in series.iterrows():
        label = cut if yearly else f"{MONTHS[int(cut[5:7]) - 1].capitalize()} {cut[:4]}"
        table_rows.append({"periodo": label, **{source: None if source not in values or values[source] != values[source]
                                               else int(values[source]) for source in SOURCE_LABELS}})
    summary = "; ".join(f"{number(item['participaciones'])} registros de {item['label'].lower()}" for item in totals)
    source_note = "Cada base conserva su propio conteo. Las cifras son participaciones en capacitación; una persona puede tener varios registros."
    if yearly and start <= "2023-11" <= end:
        source_note += " Noviembre de 2023 tiene resolución mensual."
    return {
        "key": "ferias", "label": TITLE, "icon": "graduation", "period": span, "kpis": kpis,
        "visual": {"kind": "bars", "title": "Participaciones por componente", "note": "Fuentes independientes",
                   "rows": [{"name": item["label"], "value": item["participaciones"],
                             "text": number(item["participaciones"])} for item in totals]},
        "table": {"title": "Participaciones por " + ("año" if yearly else "mes"), "note": "Registros de cada fuente",
                  "columns": [("Año" if yearly else "Mes", "periodo", None, "text"),
                              ("Empleabilidad y autoempleo", "empleabilidad_autoempleo", 164, "int"),
                              ("Inclusión económica", "inclusion_economica", 146, "int")], "rows": table_rows},
        "findings": [{"icon": "graduation", "text": summary[:1].upper() + summary[1:] + "."},
                     {"icon": "calendar", "text": source_note}],
        "update": {**corte.stamp("ferias", cut_text=span), "label": span}, "source_totals": totals,
    }


def latest_block() -> dict | None:
    from src import ferias

    data = ferias.load()
    if data.empty:
        return None
    end = str(data.periodo_id.max())
    label = f"{MONTHS[int(end[5:7]) - 1].capitalize()} de {end[:4]}"
    return period_block(end, end, label)
