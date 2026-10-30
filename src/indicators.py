"""Thematic areas and their indicators: the vocabulary every view and export shares.

Transfers and services are *territorial modules*: they read their own rows of the territorial base (never mixed) and
can be mapped by province and parish.  Labour management and the institutional budget are national areas with
their own bases.  Charts, tables and reports ask a module for its indicators instead of naming columns, so a new
family of indicators (contingencies, for instance) only needs a new entry here and its rows in the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Indicator:
    key: str          # column in the data
    label: str        # name shown to readers ("Beneficiarios", "Presupuesto acumulado 2023–2026")
    kind: str         # "count", "money" or "rate"
    icon: str         # icon name in src/ui.py and assets/icons/png
    unit: str = ""    # noun for counts ("beneficiarios", "unidades")
    short: str = ""   # shorter name for tight controls ("Acumulado 2023–2026")

    @property
    def is_money(self) -> bool:
        return self.kind == "money"

    @property
    def is_rate(self) -> bool:
        return self.kind == "rate"

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
    short_label: str = ""

    def money(self, year: int, *, executed: bool = False) -> dict[str, Indicator]:
        """Budget indicators whose names carry the period's year.

        With the accrued budget of a cut (``executed``) the period's budget is the executed budget; the annual
        references only report a budget.  The government accumulation adds this administration's budgets (from
        2023) up to the period.
        """
        span = f"2023–{year - 1}" if year - 1 > 2023 else "2023"
        return {
            "fiscal": Indicator("monto_fiscal", f"Presupuesto ejecutado {year}" if executed else f"Presupuesto {year}", "money",
                                "banknote", short=f"Ejecutado {year}" if executed else f"Presupuesto {year}"),
            "coded": Indicator("presupuesto_codificado", f"Presupuesto codificado {year}", "money", "wallet",
                               short=f"Codificado {year}"),
            "execution": Indicator("porcentaje_ejecucion", "Ejecución presupuestaria", "rate", "target", short="Ejecución"),
            "previous": Indicator("monto_anterior", f"Presupuesto acumulado {span}", "money", "landmark",
                                  short=f"Acumulado {span}"),
            "government": Indicator("monto_gobierno", f"Presupuesto acumulado 2023–{year}", "money", "landmark",
                                    short=f"Acumulado 2023–{year}"),
        }

    def people_indicator(self) -> Indicator:
        return Indicator("usuarios", self.people, "count", self.people_icon, self.people.lower())

    def indicators(self, year: int, *, executed: bool = False, parishes: bool = False, budget: bool = True) -> list[Indicator]:
        """Indicators a reader can map and rank, in reading order.

        The parish detail carries coverage and the accrued budget; the accumulated budget exists by province only.
        Months without a territorial budget (``budget=False``) map coverage only.
        """
        if not budget:
            return [self.people_indicator(), *self.extra]
        money = self.money(year, executed=executed)
        if parishes:
            return [self.people_indicator(), *self.extra, money["fiscal"]]
        return [self.people_indicator(), *self.extra, money["fiscal"], money["government"]]

    def definitions(self, year: int, *, executed: bool = False) -> list[tuple[str, str]]:
        """Formal definitions for the technical sheet of the data workbook."""
        money = self.money(year, executed=executed)
        span = money["previous"].label.removeprefix("Presupuesto acumulado ")
        rows = [(self.people, self.people_definition)]
        rows += [(extra.label, EXTRA_DEFINITIONS.get(extra.key, "")) for extra in self.extra]
        if executed:
            rows += [
                (money["fiscal"].label, f"Presupuesto devengado de {year} registrado al corte, en dólares de los Estados Unidos."),
                (money["coded"].label, f"Presupuesto codificado de {year} en la base de presupuesto territorial de transferencias y servicios: total codificado en transferencias y componentes corriente e inversión distribuidos en servicios. No equivale al presupuesto aprobado MDH–MTDH ni al codificado fiscal SGDE."),
                (money["execution"].label, "Devengado dividido para el codificado de la misma base territorial. La ejecución del presupuesto fiscal SGDE se consulta en Presupuesto > Fiscal."),
            ]
        else:
            rows.append((money["fiscal"].label, f"Presupuesto reportado para {year}, en dólares de los Estados Unidos."))
        rows += [
            (money["previous"].label, f"Presupuesto acumulado de {span.replace('–', ' a ')}, en dólares de los Estados Unidos."),
            (money["government"].label, f"Acumulado de gobierno de los programas seleccionados: presupuesto acumulado de 2023 a {year - 1} más el de {year}."),
        ]
        return rows

    @property
    def people_definition(self) -> str:
        if self.people == "Beneficiarios":
            return ("Personas distintas que reciben cada bono o pensión en el mes; el total suma los beneficiarios de cada programa. "
                    "Pensión Toda Una Vida incluye a las personas adultas y a los menores de edad.")
        return (f"Usuarios reportados por modalidad de cada {self.item} y territorio en el mes. Los cortes de 2026 conservan "
                "los conteos depurados publicados; el histórico anterior proviene de resúmenes agrupados que no permiten "
                "acreditar personas únicas. La suma de meses representa coberturas mensuales, no personas distintas del período.")


EXTRA_DEFINITIONS = {"unidades": "Unidades de atención que prestan cada servicio, propias y en convenio, en el corte."}

MODULES: dict[str, Module] = {
    "transferencias": Module(
        id="transferencias", label="Transferencias monetarias no contributivas", short_label="Transferencias", sections=("bonos_pensiones",),
        description="Beneficiarios y presupuesto de los bonos y pensiones, por programa, provincia, cantón y parroquia.",
        item="programa", items="programas", people="Beneficiarios", people_icon="hand-coins",
    ),
    "servicios": Module(
        id="servicios", label="Servicios de protección social", short_label="Servicios sociales", sections=("proteccion_integral",),
        description="Usuarios, unidades de atención y presupuesto de los servicios de protección social, por servicio, "
                    "provincia, cantón y parroquia.",
        item="servicio", items="servicios", people="Usuarios", people_icon="users",
        extra=(Indicator("unidades", "Unidades de atención", "count", "building", "unidades"),),
    ),
}

# Every area of the consultation, in the order of the institutional bulletin.
AREAS: dict[str, dict] = {
    "transferencias": {"label": "Transferencias monetarias no contributivas", "short": "Transferencias", "kind": "territorial"},
    "servicios": {"label": "Servicios de protección social", "short": "Servicios sociales", "kind": "territorial"},
    "riesgos": {"label": "Plan ENOS", "short": "ENOS", "kind": "riesgos"},
    "contingencias": {"label": "Contingencias y compensaciones", "short": "Contingencias", "kind": "contingencias",
                      "description": "Bonos por orfandad por femicidio, cobertura de contingencias y eventos de origen natural o "
                                     "antrópico, y mecanismos de compensación: personas, montos y presupuesto de cada mes."},
    "jovenes": {"label": "Jóvenes en Acción", "short": "Jóvenes en Acción", "kind": "jovenes",
                "description": "Jóvenes registrados y habilitados, transferencias acreditadas y ejecución presupuestaria de "
                               "cada fase del programa."},
    "laboral": {"label": "Empleo", "short": "Empleo", "kind": "laboral",
                "description": "Contratos de trabajo vigentes en el país por provincia y cantón, su perfil, y las "
                               "compensaciones jubilares pagadas a exservidores y extrabajadores públicos."},
    "cdh": {"label": "Crédito de Desarrollo Humano", "short": "Crédito (CDH)", "kind": "cdh",
            "description": "Créditos de Desarrollo Humano desembolsados cada mes, su perfil, actividad productiva y territorio, y la "
                           "cartera vigente."},
    "brigadas": {"label": "Brigadas sociales", "short": "Brigadas sociales", "kind": "brigadas",
                 "description": "Brigadas sociales por el Nuevo Ecuador: población alcanzada y atendida por mes, territorio y tipo."},
    "ferias": {"label": "Ferias de Empleabilidad y Autoempleo", "short": "Ferias", "kind": "ferias",
               "description": "Capacitación para la empleabilidad, el autoempleo y la inclusión económica, por mes, territorio y perfil."},
    "presupuesto": {"label": "Presupuesto institucional", "short": "Presupuesto", "kind": "presupuesto",
                    "description": "Presupuesto codificado, devengado y ejecución del Ministerio, por programa, zona y "
                                   "grupo de gasto."},
}

BUDGET_DEFINITIONS = [
    ("Presupuesto codificado", "Asignación presupuestaria vigente al corte, después de las modificaciones del año."),
    ("Presupuesto devengado", "Obligaciones de pago reconocidas al corte por bienes, servicios, obras y transferencias recibidos."),
    ("Ejecución presupuestaria", "Presupuesto devengado sobre presupuesto codificado, en porcentaje."),
    ("Saldo por devengar", "Presupuesto codificado menos presupuesto devengado."),
    ("Presupuesto certificado", "Valor certificado que registra la base financiera para cada partida."),
]


def module_for_sections(sections) -> Module:
    """The module that owns a set of data sections (exports receive already filtered rows)."""
    wanted = set(sections)
    for module in MODULES.values():
        if wanted <= set(module.sections):
            return module
    raise ValueError("La selección combina ámbitos distintos; genere un reporte por ámbito.")
