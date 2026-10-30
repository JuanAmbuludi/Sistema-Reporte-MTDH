"""Undated phase-four monitoring remains separate from dated youth payments."""
from __future__ import annotations

from src import corte
from src.reports.context import number

TITLE = "Jóvenes en Acción · Fase 4: monitoreo de transferencias"
SCOPE = "Cuarto período · corte sin fecha"


def block() -> dict | None:
    from src import jovenes_fase4

    entities = jovenes_fase4.payments()
    if entities.empty:
        return None
    stats = jovenes_fase4.summary()
    reasons = (jovenes_fase4.rejections().groupby(["codigo_rechazo", "motivo"], as_index=False)
               .transferencias.sum().sort_values("transferencias", ascending=False))
    reasons["motivo"] = reasons.motivo.map(jovenes_fase4.reason_label)
    failed = float(stats["no_acreditadas"])
    reasons["participacion"] = reasons.transferencias / failed * 100 if failed else 0
    kpis = [
        {"label": "Jóvenes seleccionados", "value": stats["seleccionados"], "kind": "count", "note": "Según la fuente de fase 4"},
        {"label": "Jóvenes autorizados", "value": stats["autorizados"], "kind": "count", "note": f"{number(stats['sin_autorizacion'])} sin autorización"},
        {"label": "Transferencias acreditadas", "value": stats["acreditadas"], "kind": "count", "note": f"USD {number(stats['monto_acreditado'] / 1e6, 1)} M"},
        {"label": "Transferencias no acreditadas", "value": stats["no_acreditadas"], "kind": "count", "note": f"USD {number(stats['monto_no_acreditado'] / 1e6, 1)} M"},
        {"label": "Monto acreditado", "value": stats["monto_acreditado"], "kind": "money", "decimals": 1, "note": "Fase 4 · sin fecha de corte"},
        {"label": "Monto no acreditado", "value": stats["monto_no_acreditado"], "kind": "money", "decimals": 1, "note": "Fase 4 · sin fecha de corte"},
    ]
    entity_rows = jovenes_fase4.display_entities(entities).to_dict("records")
    entity_rows.append({"entidad": "Total de la fuente", "autorizados": stats["autorizados"],
                        "acreditadas": stats["acreditadas"], "no_acreditadas": stats["no_acreditadas"],
                        "tasa_acreditacion": stats["tasa_acreditacion"], "selected": True})
    reason_rows = reasons.to_dict("records")
    reason_rows.append({"motivo": "Total no acreditado", "transferencias": stats["no_acreditadas"],
                        "participacion": 100.0 if failed else None, "selected": True})
    return {
        "key": "jovenes_fase4", "label": TITLE, "icon": "graduation", "period": SCOPE,
        "update": {**corte.stamp("jovenes_fase4", cut_text=SCOPE), "label": SCOPE, "frequency": "Según la fuente"},
        "kpis": kpis, "stats": stats, "body_h": 168,
        "visual": {"kind": "bars", "title": "Motivos de no acreditación", "note": "Cinco principales",
                   "rows": [{"name": row.motivo, "value": float(row.transferencias),
                             "text": f"{number(row.transferencias)} · {number(row.participacion, 1)} %"}
                            for row in reasons.head(5).itertuples()]},
        "table": {"title": "Autorización y acreditación por entidad", "note": f"Monto autorizado: USD {number(stats['monto_autorizado'], 2)}",
                  "columns": [("Entidad ejecutora", "entidad", None, "text"), ("Autorizados", "autorizados", 72, "int"),
                              ("Acreditadas", "acreditadas", 72, "int"), ("No acreditadas", "no_acreditadas", 80, "int"),
                              ("Acreditación", "tasa_acreditacion", 66, "pct")], "rows": entity_rows},
        "tables": [{"title": "Causas de transferencias no acreditadas", "note": "Sobre el total no acreditado",
                    "columns": [("Motivo", "motivo", None, "text"), ("Transferencias", "transferencias", 86, "int"),
                                ("Participación", "participacion", 76, "pct")], "rows": reason_rows}],
        "findings": [{"icon": "target", "text": f"Se acredita el {number(stats['tasa_acreditacion'], 2)} % de las transferencias autorizadas; {number(stats['sin_autorizacion'])} seleccionados no tienen autorización. "
                      f"Las {number(stats['no_acreditadas'])} no acreditadas se concilian con los motivos y las {number(stats['entidades'])} entidades ejecutoras."},
                     {"icon": "calendar", "text": "La fuente no informa fecha de corte ni de pago. Este monitoreo de la fase 4 se presenta como referencia independiente; no se suma a las fases 1–3 ni al acumulado del período."}],
    }
