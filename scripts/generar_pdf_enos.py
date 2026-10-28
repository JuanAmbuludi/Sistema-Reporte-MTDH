"""Exporta un período de ENOS o una publicación conservada del dashboard."""
import argparse
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.views.riesgos import RiskView
from src.reports import generate_pdf
from src import enos


def iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use una fecha válida con formato AAAA-MM-DD.") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desde", type=iso_date, help="Primera fecha del período, inclusive (AAAA-MM-DD).")
    parser.add_argument("--hasta", type=iso_date, help="Última fecha del período, inclusive (AAAA-MM-DD).")
    parser.add_argument("--todo-historial", action="store_true", help="Exportar todas las fechas disponibles; es el modo predeterminado.")
    parser.add_argument("--publicacion", type=iso_date, metavar="AAAA-MM-DD", help="Recuperar la publicación conservada de esa fecha.")
    parser.add_argument("--salida", type=Path, help="Ruta del PDF; por defecto se guarda en docs/reportes con su período.")
    args = parser.parse_args(argv)
    has_range = args.desde is not None or args.hasta is not None
    if args.publicacion is not None and (has_range or args.todo_historial):
        parser.error("--publicacion no se combina con --desde, --hasta ni --todo-historial.")
    if args.todo_historial and has_range:
        parser.error("--todo-historial no se combina con --desde ni --hasta.")
    if args.desde is not None and args.hasta is not None and args.desde > args.hasta:
        parser.error("--desde no puede ser posterior a --hasta.")
    if args.publicacion is not None and args.publicacion not in {day.date() for day, _path in enos.publications()}:
        parser.error("No existe una publicación guardada para esa fecha. Use --desde/--hasta para consultar registros por período.")

    view = RiskView()
    catalog = view.catalog()
    if not catalog:
        parser.error("No hay datos de ENOS disponibles para exportar.")
    try:
        if args.publicacion is not None:
            view.select(catalog[-1], mode="publicacion", until=args.publicacion)
            filename = f"Plan_ENOS_publicacion_{args.publicacion.isoformat()}.pdf"
        else:
            view.select(catalog[-1], mode="periodo", since=args.desde, until=args.hasta)
            filename = f"Plan_ENOS_{view.since:%Y-%m-%d}_al_{view.until:%Y-%m-%d}.pdf"
        if not view.prepare():
            parser.error(view.empty_message)
        content = generate_pdf(view.report_context("Plan ENOS"))
    except ValueError as exc:
        parser.error(str(exc))

    path = args.salida or ROOT / "docs" / "reportes" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
