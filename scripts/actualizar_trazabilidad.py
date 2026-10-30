"""Persist only actual source-content revisions, independently for each section."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.revisions import update  # noqa: E402


if __name__ == "__main__":
    registry, changed = update()
    print("Trazabilidad actualizada" if changed else "Sin cambios de contenido; fechas conservadas")
    for area, revision in registry["areas"].items():
        print(f"{area}: {revision['actualizado_utc'] or 'sin fecha verificable'}")
