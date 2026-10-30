"""Source-specific counts, filters and public schema of formation records."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.preparar_ferias import Aggregates, period, read_employment
from src import ferias


class FormationData(unittest.TestCase):
    def test_numeric_and_named_months_have_same_period(self):
        for month in ('Septiembre','SEPTIEMBRE','9',9,9.0):
            self.assertEqual(period(2026.0,month),'2026-09')
        with self.assertRaises(ValueError):period(2026,0)
        with self.assertRaises(ValueError):period(2026,'Sin mes')

    def test_aggregation_keeps_independent_source_lines_and_does_not_double_sessions(self):
        agg=Aggregates()
        args=('2026-09','Manabí','Chone','PRESENCIAL','Individual',{'sexo':'Mujeres','edad':'30 a 45 años'})
        agg.add('inclusion_economica',*args)
        agg.add('inclusion_economica',*args)
        agg.add('empleabilidad_autoempleo',*args)
        rows,profiles=agg.frames()
        self.assertEqual(rows.groupby('fuente').participaciones.sum().to_dict(),{'inclusion_economica':2,'empleabilidad_autoempleo':1})
        self.assertEqual(set(rows.provincia_codigo),{'13'})
        self.assertEqual(profiles.groupby('dimension').participaciones.sum().to_dict(),{'edad':3,'sexo':3})
        self.assertNotIn('Cedula',rows)
        self.assertNotIn('RUC',rows)

    def test_period_and_territory_filters_are_inclusive(self):
        agg=Aggregates()
        for month,province in [('2026-08','Guayas'),('2026-09','Guayas'),('2026-09','Manabí')]:
            agg.add('inclusion_economica',month,province,'Canton','PRESENCIAL','Individual',{})
        rows,_=agg.frames()
        filtered=ferias.select(rows,fuente='inclusion_economica',since='2026-08',until='2026-09',provinces=['09'])
        self.assertEqual(ferias.summary(filtered)['participaciones'],2)
        self.assertEqual(ferias.summary(filtered)['provincias'],1)
        self.assertEqual(ferias.summary(filtered)['meses'],2)
        self.assertEqual(ferias.select(rows,since='2026-10').shape[0],0)

    def test_csv_removes_only_wholly_identical_rows(self):
        row={'Año':'2026','Mes':'Septiembre','Cedula':'example-local-only','Provincia':'Guayas','Canton':'Guayaquil',
             'Modalidad':'PRESENCIAL','Componente':'TECNICO','Genero':'FEMENINO','Rango de Edad':'Edad 30 a 45 años',
             'Tipo Zona':'URBANA','Tipo Actividad':'SERVICIOS','Institucion':'Instituto público','Tema':'Tema A'}
        source=pd.DataFrame([row,row,{**row,'Tema':'Tema B'}])
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'source.csv';source.to_csv(path,index=False,encoding='cp1252')
            aggregate=Aggregates();control=read_employment(path,aggregate,'2023-11')
        self.assertEqual(control['registros'],2)
        self.assertEqual(control['duplicados_eliminados'],1)
        self.assertEqual(aggregate.frames()[0].participaciones.sum(),2)


if __name__=='__main__':unittest.main()
