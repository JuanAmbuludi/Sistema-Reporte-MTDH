"""Thematic modules and their indicators: the vocabulary every view and export shares.

Each module reads only its own rows (transfers are never mixed with services).  Charts, tables and reports
ask a module for its indicators instead of naming columns, so a new family of indicators (contingency or
labour figures, for instance) only needs a new ``Module`` here and its rows in the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Indicator:
    key: str          # column in the data
    label: str        # name shown to readers ("Beneficiarios", "Presupuesto acumulado 2023–2026")
    kind: str         # "count" or "money"
    icon: str         # icon name in src/ui.py and assets/icons/png
    unit: str = ""    # noun for counts ("beneficiarios", "unidades")
    short: str = ""   # shorter name for tight controls ("Acumulado 2023–2026")

    @property
    def is_money(self) -> bool:
        return self.kind == "money"

    @property
    def compact(self) -> str:
        return self.short or self.label


@dataclass(frozen=True)
class Module:
    id: str
    label: str
    sections: tuple[str, ...]
    description: str
    item: str                 # one row of the category axis: "programa", "servicio"
    items: str                # plural
    people: str               # "Beneficiarios", "Usuarios"
    people_icon: str
    extra: tuple[Indicator, ...] = field(default_factory=tuple)

    def money(self, year: int, *, executed: bool = False) -> dict[str, Indicator]:
        """Budget indicators whose names carry the period's year.

        The government accumulation adds the budgets of this administration (from 2023) up to the period.
        """
        span = f"2023–{year - 1}" if year - 1 > 2023 else "2023"
        return {
            "fiscal": Indicator("monto_fiscal", f"Presupuesto ejecutado {year}" if executed else f"Presupuesto {year}", "money", "banknote",
                                short=f"Ejecutado {year}" if executed else f"Presupuesto {year}"),
            "previous": Indicator("monto_anterior", f"Presupuesto acumulado {span}", "money", "landmark",
                                  short=f"Acumulado {span}"),
            "government": Indicator("monto_gobierno", f"Presupuesto acumulado 2023–{year}", "money", "landmark",
                                    short=f"Acumulado 2023–{year}"),
        }

    def people_indicator(self) -> Indicator:
        return Indicator("usuarios", self.people, "count", self.people_icon, self.people.lower())

    def indicators(self, year: int, *, executed: bool = False) -> list[Indicator]:
        """Indicators a reader can map and rank, in reading order."""
        money = self.money(year, executed=executed)
        return [self.people_indicator(), *self.extra, money["fiscal"], money["government"]]

    def definitions(self, year: int, *, executed: bool = False) -> list[tuple[str, str]]:
        """Formal definitions for the technical sheet of the data workbook."""
        money = self.money(year, executed=executed)
        span = money["previous"].label.removeprefix("Presupuesto acumulado ").removeprefix("Presupuesto ")
        rows = [(self.people, self.people_definition)]
        rows += [(extra.label, EXTRA_DEFINITIONS.get(extra.key, "")) for extra in self.extra]
        rows += [
            (money["fiscal"].label, f"Devengado fiscal reportado al corte de {year}; no es exclusivamente el gasto del mes." if executed else f"Presupuesto reportado en {year}; la fuente histórica no identifica su fase presupuestaria."),
            (money["previous"].label, f"Acumulado reportado en {span}, en dólares de los Estados Unidos."),
            (money["government"].label, f"Acumulado anterior más el presupuesto fiscal de {year}; no sumar nuevamente sus componentes."),
        ]
        return rows

    @property
    def people_definition(self) -> str:
        if self.people == "Beneficiarios":
            return "Beneficiarios reportados por bono o pensión; agregados sin deduplicación entre programas."
        return f"Usuarios reportados por {self.item}; agregados sin deduplicación entre modalidades."


EXTRA_DEFINITIONS = {"unidades": "Unidades reportadas en la base de cobertura; sin identificadores para deduplicarlas entre modalidades y cooperantes."}


MODULES: dict[str, Module] = {
    "transferencias": Module(
        id="transferencias", label="Transferencias monetarias", sections=("bonos_pensiones",),
        description="Beneficiarios y presupuesto de los bonos y pensiones, por programa y provincia.",
        item="programa", items="programas", people="Beneficiarios", people_icon="hand-coins",
    ),
    "servicios": Module(
        id="servicios", label="Servicios de protección integral", sections=("proteccion_integral",),
        description="Usuarios, unidades de atención y presupuesto de los servicios de protección integral, por servicio y provincia.",
        item="servicio", items="servicios", people="Usuarios", people_icon="users",
        extra=(Indicator("unidades", "Unidades de atención", "count", "building", "unidades"),),
    ),
}


def module_for_sections(sections) -> Module:
    """The module that owns a set of data sections (exports receive already filtered rows)."""
    wanted = set(sections)
    for module in MODULES.values():
        if wanted <= set(module.sections):
            return module
    raise ValueError("La selección combina ámbitos distintos; genere un reporte por ámbito.")
