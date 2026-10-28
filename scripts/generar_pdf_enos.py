"""Genera el PDF de Plan ENOS desde el mismo contexto utilizado por el dashboard."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.views.riesgos import RiskView
from src.reports import generate_pdf

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--salida',default='docs/reportes/Plan_ENOS_2026-10-27_actualizado.pdf')
    args=p.parse_args()
    v=RiskView();v.select(v.catalog()[-1]);assert v.prepare()
    path=Path(args.salida);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(generate_pdf(v.report_context('Plan ENOS')))
    print(path)
