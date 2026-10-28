"""Agrega las bases nominales de Crédito de Desarrollo Humano (CDH) y de Brigadas sociales sin datos personales.

Uso (los insumos nominales nunca se versionan):

    python -I scripts/preparar_cdh_brigadas.py --cdh-historico CDH_HISTORICO_2026.parquet \
        --cdh-vigente CDH_BASE_VIGENTE.parquet --brigadas RESULTADOS_BRIGADAS_SOCIALES.xlsx

Escribe en ``data/processed``: ``cdh_territorio.parquet`` (créditos y monto por mes, parroquia, bono y plazo),
``cdh_perfil.parquet`` (por mes, provincia, bono, sexo, edad, actividad y área), ``brigadas.parquet`` (una fila por brigada,
sin lugar ni responsables) y ``cdh_brigadas.json`` (fuentes, cortes y totales de control).  No se guardan cédulas,
nombres, teléfonos ni direcciones.
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"


def _key(text) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(text.replace("-", " ").split())


def _title(text) -> str:
    small = {"de", "del", "la", "las", "los", "y", "el", "en", "a"}
    words = str(text or "").strip().lower().split()
    return " ".join(w if i and w in small else w[:1].upper() + w[1:] for i, w in enumerate(words))


PLAZO = {"CDH 24 MESES": "24 meses", "24 MESES": "24 meses", "CDH 12 MESES": "12 meses", "12 MESES": "12 meses"}
BONO = {"BONO DE DESARROLLO HUMANO": "Bono de Desarrollo Humano", "BONO VARIABLE": "BDH con componente variable",
        "PENSIÓN TODA UNA VIDA": "Pensión Toda Una Vida", "MIS MEJORES AÑOS": "Pensión Mis Mejores Años"}
ACTIVIDAD = {"AGRICULTURA, GANADERÍA, SILVICULTURA Y PESCA": "Agricultura, ganadería, silvicultura y pesca",
             "COMERCIO AL POR MAYOR Y AL POR MENOR, REPARACIÓN DE VEHÍCULOS AUTOMOTORES Y MOTOCICLETAS": "Comercio",
             "ACTIVIDADES DE ALOJAMIENTO Y DE SERVICIO DE COMIDAS": "Alojamiento y servicio de comidas",
             "INDUSTRIA MANUFACTURERA": "Industria manufacturera", "OTRAS ACTIVIDADES DE SERVICIOS": "Otras actividades de servicios"}
EDAD = {"EDAD 18 A 29 AÑOS": "18 a 29 años", "EDAD 30 A 45 AÑOS": "30 a 45 años", "EDAD 46 A 65 AÑOS": "46 a 65 años",
        "MAYOR A 65 AÑOS TERCERA EDAD": "Más de 65 años"}


def credits(historico: Path, vigente: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    frames = []
    for path, fuente in ((historico, "desembolso"), (vigente, "vigente")):
        d = pd.read_parquet(path)
        frame = pd.DataFrame({
            "fuente": fuente, "periodo": d.PERIODO_ARCHIVO.astype(str).str[:7],
            "provincia_codigo": d.DPA_COD_PROVINCIA.astype(str).str.zfill(2), "provincia": d.DPA_PROVINCIA.map(_title),
            "canton_codigo": d.DPA_COD_CANTON.astype(str).str.zfill(4), "canton": d.DPA_CANTON.map(_title),
            "parroquia_codigo": d.DPA_COD_PARROQUIA.astype(str).str.zfill(6), "parroquia": d.DPA_PARROQUIA.map(_title),
            "bono": d.TIPO_SUBSIDIO.map(BONO).fillna("Otro"), "plazo": d.TIPO_CREDITO.map(PLAZO).fillna("Otro"),
            "actividad": d.TIPO_ACTIVIDAD.map(ACTIVIDAD).fillna("Sin actividad registrada"),
            "sexo": d.GENERO.map({"FEMENINO": "Mujeres", "MASCULINO": "Hombres"}).fillna("Sin dato"),
            "edad": d.RANGO_EDAD.map(EDAD).fillna("Sin dato"), "area": d.TIPO_ZONA.map({"URBANA": "Urbana", "RURAL": "Rural"}).fillna("Sin dato"),
            "monto": pd.to_numeric(d.MONTO, errors="coerce").fillna(0.0),
        })
        frames.append(frame)
    rows = pd.concat(frames, ignore_index=True)
    territory = (rows.groupby(["fuente", "periodo", "provincia_codigo", "provincia", "canton_codigo", "canton", "parroquia_codigo",
                               "parroquia", "bono", "plazo"], as_index=False)
                 .agg(creditos=("monto", "size"), monto=("monto", "sum")))
    profile = (rows.groupby(["fuente", "periodo", "provincia_codigo", "bono", "sexo", "edad", "actividad", "area"], as_index=False)
               .agg(creditos=("monto", "size"), monto=("monto", "sum")))
    control = {f: {"creditos": int((rows.fuente == f).sum()), "monto": round(float(rows.loc[rows.fuente == f, "monto"].sum()), 2),
                   "periodos": sorted(rows.loc[rows.fuente == f, "periodo"].unique().tolist())} for f in ("desembolso", "vigente")}
    return territory, profile, control


def brigades(path: Path, provinces: dict[str, tuple[str, str]]) -> tuple[pd.DataFrame, dict]:
    d = pd.read_excel(path, sheet_name=0)
    d.columns = [" ".join(str(c).split()).upper() for c in d.columns]
    d = d.loc[pd.to_datetime(d["FECHA"], errors="coerce").notna()].copy()
    fecha = pd.to_datetime(d["FECHA"], errors="coerce")
    code = d["PROVINCIA"].map(lambda p: provinces.get(_key(p), (None, None))[0])
    name = d["PROVINCIA"].map(lambda p: provinces.get(_key(p), (None, _title(p)))[1])
    tipo = d["TIPO DE BRIGADA"].map(lambda t: " ".join(str(t).replace("-", " - ").split()).replace(" - ", " · "))
    frame = pd.DataFrame({
        "fecha": fecha.dt.date.astype(str), "periodo": fecha.dt.strftime("%Y-%m"), "provincia_codigo": code, "provincia": name,
        "canton": d["CANTON"].map(_title), "parroquia": d["PARROQUIA"].map(_title),
        "tipo": tipo.map(lambda t: _title(t).replace("Mtdh", "MTDH").replace("Mdg", "MDG").replace("Presi", "Presidencia").replace("Tipo a", "Tipo A")),
        "alcanzada": pd.to_numeric(d["POBLACIÓN ALCANZADA"], errors="coerce").fillna(0).astype(int),
        "atendida": pd.to_numeric(d["POBLACION ATENDIDA"], errors="coerce").fillna(0).astype(int),
    }).sort_values("fecha").reset_index(drop=True)
    control = {"brigadas": int(len(frame)), "alcanzada": int(frame.alcanzada.sum()), "atendida": int(frame.atendida.sum()),
               "desde": frame.fecha.min(), "hasta": frame.fecha.max(), "sin_provincia": int(frame.provincia_codigo.isna().sum())}
    return frame, control


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cdh-historico", type=Path, required=True)
    parser.add_argument("--cdh-vigente", type=Path, required=True)
    parser.add_argument("--brigadas", type=Path, required=True)
    args = parser.parse_args()
    territory, profile, control = credits(args.cdh_historico, args.cdh_vigente)
    provinces = {_key(n): (c, n) for c, n in territory[["provincia_codigo", "provincia"]].drop_duplicates().itertuples(index=False)}
    provinces.update({"STO DOMINGO DE LOS TSACHILAS": provinces.get("SANTO DOMINGO DE LOS TSACHILAS", (None, None))})
    brigade_rows, brigade_control = brigades(args.brigadas, provinces)
    OUT.mkdir(parents=True, exist_ok=True)
    territory.to_parquet(OUT / "cdh_territorio.parquet", index=False)
    profile.to_parquet(OUT / "cdh_perfil.parquet", index=False)
    brigade_rows.to_parquet(OUT / "brigadas.parquet", index=False)
    manifest = {"generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "cdh": {"fuentes": {"desembolso": args.cdh_historico.name.split("-", 1)[-1], "vigente": args.cdh_vigente.name.split("-", 1)[-1]},
                        "control": control,
                        "alcance": "Créditos de Desarrollo Humano desembolsados en 2026 por mes de archivo y cartera vigente al último corte. "
                                   "Agregado sin datos personales."},
                "brigadas": {"fuente": args.brigadas.name.split("-", 1)[-1], "control": brigade_control,
                             "alcance": "Brigadas sociales por el Nuevo Ecuador: una fila por brigada con su fecha, territorio, tipo, "
                                        "población alcanzada y atendida. Sin lugar ni responsables."}}
    (OUT / "cdh_brigadas.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    main()
