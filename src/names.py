"""Readable Spanish names for places and budget categories that arrive in upper case without accents.

Sources write ``SAN JOSE DE MINAS`` or ``PROTECCION SOCIAL A LA FAMILIA``; the dashboard and every export
show ``San José de Minas`` and ``Protección social a la familia``.  Accents are restored from a vocabulary of
the words that actually appear in the bases (Ecuadorian toponymy and budget terms), never guessed by rule.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

# Upper-case word without accent -> upper-case word with its accent (or diaeresis).
_ACCENTS = {
    # Toponymy of parishes, cantons and districts
    "ABAÑIN": "ABAÑÍN", "ABDON": "ABDÓN", "AGRICOLA": "AGRÍCOLA", "ALANGASI": "ALANGASÍ", "ALAQUEZ": "ALÁQUEZ",
    "ALAUSI": "ALAUSÍ", "ALLURIQUIN": "ALLURIQUÍN", "ALOAG": "ALÓAG", "ALOASI": "ALOASÍ", "AMBUQUI": "AMBUQUÍ",
    "AMERICA": "AMÉRICA", "ANCON": "ANCÓN", "ANDRES": "ANDRÉS", "ANGEL": "ÁNGEL", "ANGELES": "ÁNGELES",
    "ANIBAL": "ANÍBAL", "ASUNCION": "ASUNCIÓN", "AVILA": "ÁVILA", "AZUCAR": "AZÚCAR", "BAHIA": "BAHÍA",
    "BALLEN": "BALLÉN", "BARBARA": "BÁRBARA", "BARTOLOME": "BARTOLOMÉ", "BATAN": "BATÁN", "BENITEZ": "BENÍTEZ",
    "BIBLIAN": "BIBLIÁN", "BILIAN": "BIBLIÁN", "BILOVAN": "BILOVÁN", "BOLIVAR": "BOLÍVAR", "BOMBOLI": "BOMBOLÍ",
    "BOMBON": "BOMBÓN", "BORBON": "BORBÓN", "BOYACA": "BOYACÁ", "BULAN": "BULÁN", "CACHAVI": "CACHAVÍ",
    "CAHUASQUI": "CAHUASQUÍ", "CALACALI": "CALACALÍ", "CALAZACON": "CALAZACÓN", "CALDERON": "CALDERÓN",
    "CALPAQUI": "CALPAQUÍ", "CANGONAMA": "CANGONAMÁ", "CAPITAN": "CAPITÁN", "CARAQUEZ": "CARÁQUEZ",
    "CARCABON": "CARCABÓN", "CARCELEN": "CARCELÉN", "CARIGAN": "CARIGÁN", "CARRION": "CARRIÓN",
    "CATANAHUAN": "CATANAHUÁN", "CELEN": "CELÉN", "CESAR": "CÉSAR", "CHANTILIN": "CHANTILÍN", "CHAVES": "CHÁVES",
    "CHICAN": "CHICÁN", "CHIGUINDA": "CHIGÜINDA", "CHITAN": "CHITÁN", "CHUGCHILLAN": "CHUGCHILLÁN",
    "CHUMBLIN": "CHUMBLÍN", "COJIMIES": "COJIMÍES", "COLON": "COLÓN", "COMITE": "COMITÉ", "CONCEPCION": "CONCEPCIÓN",
    "CONDOR": "CÓNDOR", "CORAZON": "CORAZÓN", "CORDOVA": "CÓRDOVA", "COTALO": "COTALÓ", "CRISTOBAL": "CRISTÓBAL",
    "CUBIJIES": "CUBIJÍES", "CUMANDA": "CUMANDÁ", "CUMBAYA": "CUMBAYÁ", "DAVALOS": "DÁVALOS", "DAVILA": "DÁVILA",
    "DIAZ": "DÍAZ", "DOMINGUEZ": "DOMÍNGUEZ", "DURAN": "DURÁN", "ECHEANDIA": "ECHEANDÍA", "EDEN": "EDÉN",
    "ENRIQUEZ": "ENRÍQUEZ", "ESPINDOLA": "ESPÍNDOLA", "FARFAN": "FARFÁN", "FATIMA": "FÁTIMA",
    "FERNANDEZ": "FERNÁNDEZ", "GALAN": "GALÁN", "GALAPAGOS": "GALÁPAGOS", "GARCIA": "GARCÍA", "GIRON": "GIRÓN",
    "GOMEZ": "GÓMEZ", "GONZALEZ": "GONZÁLEZ", "GONZANAMA": "GONZANAMÁ", "GUACHANAMA": "GUACHANAMÁ",
    "GUAMANI": "GUAMANÍ", "GUAMBALO": "GUAMBALÓ", "GUANAZAN": "GUANAZÁN", "GUAPAN": "GUAPÁN",
    "GUAYACAN": "GUAYACÁN", "GUEL": "GÜEL", "GUTIERREZ": "GUTIÉRREZ", "HISTORICO": "HISTÓRICO",
    "HOLGUIN": "HOLGUÍN", "HUAMBALO": "HUAMBALÓ", "HUAYNACAPAC": "HUAYNACÁPAC", "ILUMAN": "ILUMÁN", "INES": "INÉS",
    "ISINLIVI": "ISINLIVÍ", "ITCHIMBIA": "ITCHIMBÍA", "JADAN": "JADÁN", "JAMBELI": "JAMBELÍ", "JARAMIJO": "JARAMIJÓ",
    "JELI": "JELÍ", "JERUSALEN": "JERUSALÉN", "JESUS": "JESÚS", "JIJON": "JIJÓN", "JOAQUIN": "JOAQUÍN",
    "JORDAN": "JORDÁN", "JOSE": "JOSÉ", "JUJAN": "JUJÁN", "JUMON": "JUMÓN", "JUNIN": "JUNÍN", "LEON": "LEÓN",
    "LEONIDAS": "LEÓNIDAS", "LICAN": "LICÁN", "LIMON": "LIMÓN", "LOPEZ": "LÓPEZ", "LUCIA": "LUCÍA",
    "LUMBAQUI": "LUMBAQUÍ", "MACARA": "MACARÁ", "MACHANGARA": "MACHÁNGARA", "MALCHINGUI": "MALCHINGUÍ",
    "MANA": "MANÁ", "MANABI": "MANABÍ", "MARCABELI": "MARCABELÍ", "MARIA": "MARÍA", "MARIN": "MARÍN",
    "MARTIN": "MARTÍN", "MARTINEZ": "MARTÍNEZ", "MEJIA": "MEJÍA", "MENDEZ": "MÉNDEZ", "MISAHUALLI": "MISAHUALLÍ",
    "MONTUFAR": "MONTÚFAR", "MORAN": "MORÁN", "MULALO": "MULALÓ", "NABON": "NABÓN", "NAYON": "NAYÓN",
    "NAZON": "NAZÓN", "NICOLAS": "NICOLÁS", "OTON": "OTÓN", "PAJAN": "PAJÁN", "PARAISO": "PARAÍSO",
    "PATAQUI": "PATAQUÍ", "PATULU": "PATULÚ", "PENINSULA": "PENÍNSULA", "PICOAZA": "PICOAZÁ", "PIJILI": "PIJILÍ",
    "PILAGUIN": "PILAGÜÍN", "PILAGÜIN": "PILAGÜÍN", "PILAHUIN": "PILAHUÍN", "PILALO": "PÍLALO", "PILLARO": "PÍLLARO",
    "PINAS": "PIÑAS", "PINGUILI": "PINGUILÍ", "PINTAG": "PÍNTAG", "PLACIDO": "PLÁCIDO", "PLAYON": "PLAYÓN",
    "POALO": "POALÓ", "PUCARA": "PUCARÁ", "PUENGASI": "PUENGASÍ", "PUJILI": "PUJILÍ", "PUNA": "PUNÁ",
    "PUNGALA": "PUNGALÁ", "PUNIN": "PUNÍN", "QUIMIAG": "QUÍMIAG", "QUININDE": "QUININDÉ", "RAMIREZ": "RAMÍREZ",
    "RAMON": "RAMÓN", "REGULO": "RÉGULO", "RENDON": "RENDÓN", "RIO": "RÍO", "RIOFRIO": "RIOFRÍO", "RIOS": "RÍOS",
    "RODRIGUEZ": "RODRÍGUEZ", "RUMINAHUI": "RUMIÑAHUI", "SALATI": "SALATÍ", "SAMBORONDON": "SAMBORONDÓN",
    "SANGOLQUI": "SANGOLQUÍ", "SANGUILLIN": "SANGUILLÍN", "SAQUISILI": "SAQUISILÍ", "SATELITE": "SATÉLITE",
    "SAYAUSI": "SAYAUSÍ", "SEBASTIAN": "SEBASTIÁN", "SIMON": "SIMÓN", "SINAI": "SINAÍ", "SOFIA": "SOFÍA",
    "SUA": "SÚA", "SUAREZ": "SUÁREZ", "SUCUA": "SUCÚA", "SUCUMBIOS": "SUCUMBÍOS", "TABLON": "TABLÓN",
    "TELEMBI": "TELEMBÍ", "TERAN": "TERÁN", "TIXAN": "TIXÁN", "TOMAS": "TOMÁS", "TONCHIGUE": "TONCHIGÜE",
    "TSACHILAS": "TSÁCHILAS", "TULCAN": "TULCÁN", "TULULBI": "TULULBÍ", "UNION": "UNIÓN", "URCUQUI": "URCUQUÍ",
    "VALPARAISO": "VALPARAÍSO", "VASQUEZ": "VÁSQUEZ", "VICTOR": "VÍCTOR", "YAMANA": "YAMANÁ", "YARUQUI": "YARUQUÍ",
    "YARUQUIES": "YARUQUÍES", "YASUNI": "YASUNÍ", "YULUC": "YÚLUC", "ZAMBIZA": "ZÁMBIZA", "ZARATE": "ZÁRATE",
    # Administrative and budget vocabulary
    "ACCION": "ACCIÓN", "ADMINISTRACION": "ADMINISTRACIÓN", "ADOPCION": "ADOPCIÓN", "ANOS": "AÑOS",
    "ARTICULACION": "ARTICULACIÓN", "ASESORIA": "ASESORÍA", "ATENCION": "ATENCIÓN", "AUTOMATIZACION": "AUTOMATIZACIÓN",
    "COMPENSACION": "COMPENSACIÓN", "COMUNICACION": "COMUNICACIÓN", "COORDINACION": "COORDINACIÓN",
    "DIALOGO": "DIÁLOGO", "DIAS": "DÍAS", "DIRECCION": "DIRECCIÓN", "DISENO": "DISEÑO", "ECONOMICA": "ECONÓMICA",
    "EJECUCION": "EJECUCIÓN", "ERRADICACION": "ERRADICACIÓN", "ESTRATEGICA": "ESTRATÉGICA", "EVALUACION": "EVALUACIÓN",
    "FORMULACION": "FORMULACIÓN", "GENERACION": "GENERACIÓN", "GERONTOLOGICA": "GERONTOLÓGICA",
    "GERONTOLOGICOS": "GERONTOLÓGICOS", "GESTION": "GESTIÓN", "IMPLEMENTACION": "IMPLEMENTACIÓN",
    "INCLUSION": "INCLUSIÓN", "INFORMACION": "INFORMACIÓN", "INNOVACION": "INNOVACIÓN", "INVERSION": "INVERSIÓN",
    "JOVENES": "JÓVENES", "JURIDICA": "JURÍDICA", "MISION": "MISIÓN", "NINAS": "NIÑAS", "NINOS": "NIÑOS",
    "PARTICIPACION": "PARTICIPACIÓN", "PENSION": "PENSIÓN", "PLANIFICACION": "PLANIFICACIÓN", "POLITICAS": "POLÍTICAS",
    "POLITICA": "POLÍTICA", "PRESTACION": "PRESTACIÓN", "PRESTAMOS": "PRÉSTAMOS", "PREVENCION": "PREVENCIÓN",
    "PROTECCION": "PROTECCIÓN", "PUBLICAS": "PÚBLICAS", "PUBLICA": "PÚBLICA", "PUBLICO": "PÚBLICO",
    "PUBLICOS": "PÚBLICOS", "RECTORIA": "RECTORÍA", "SITUACION": "SITUACIÓN", "SOCIOECONOMICA": "SOCIOECONÓMICA",
    "TECNICA": "TÉCNICA", "TECNOLOGIAS": "TECNOLOGÍAS", "TRANSFORMACION": "TRANSFORMACIÓN",
}
# Words written in capitals whatever the casing of the rest.
_ACRONYMS = {"CDI", "CNH", "DII", "INEC", "MDH", "MIES", "MSP", "MTDH", "USD", "VIS", "VIE", "SUT", "DMQ"}
_PARTICLES = {"a", "al", "de", "del", "e", "el", "en", "la", "las", "los", "o", "para", "por", "u", "y", "con", "sin"}
_WORD = re.compile(r"[^\W\d_]+")


def _missing(text: object) -> bool:
    return text is None or (not isinstance(text, str) and pd.isna(text)) or not str(text).strip()


def _words(raw: str, sentence: bool) -> str:
    """Case every word of an upper-case text, restoring accents; ``sentence`` keeps only the first capital."""
    parts = _WORD.split(raw)
    tokens = _WORD.findall(raw)
    # "10 DE AGOSTO" starts with a number: its particles stay in lower case.
    out, first = [parts[0]], not parts[0].strip()
    for index, token in enumerate(tokens):
        following = parts[index + 1]
        word = _ACCENTS.get(token, token)
        if word in _ACRONYMS:
            out.append(word)
        elif len(word) == 1 and following.startswith("."):
            out.append(word)  # an initial: Julio E. Moreno
        else:
            lower = word.lower()
            if not first and (sentence or lower in _PARTICLES):
                out.append(lower)
            else:
                out.append(lower[:1].upper() + lower[1:])
        first = False
        out.append(following)
    return "".join(out)


def key(text: object) -> str:
    """Comparison key: upper case, without accents, parentheses or extra spaces (Ñ is kept)."""
    if _missing(text):
        return ""
    raw = re.sub(r"\s*\(.*$", "", " ".join(str(text).split()).upper())
    raw = raw.replace("Ñ", "\0")
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    return raw.replace("\0", "Ñ").strip()


def place(text: object, *, short: bool = True) -> str:
    """Parish, canton or province name: ``SAN JOSE DE MINAS`` → ``San José de Minas``.

    ``short`` drops alternative names in parentheses (``BARTOLOMÉ RUIZ (CÉSAR FRANCO CARRIÓN)`` → ``Bartolomé
    Ruiz``) so charts and tooltips stay legible; the full official form keeps them.
    """
    if _missing(text):
        return "—"
    raw = " ".join(str(text).split()).upper()
    if short:
        raw = re.sub(r"\s*\(.*$", "", raw)
    raw = re.sub(r"\s*-\s*", "-", raw).strip(" -")
    return _words(raw, sentence=False)


def sentence(text: object) -> str:
    """Administrative text in sentence case: ``SERVICIOS DE ATENCION GERONTOLOGICA`` → ``Servicios de atención
    gerontológica``."""
    if _missing(text):
        return "—"
    raw = " ".join(str(text).replace("·", " ").split()).upper()
    return _words(raw, sentence=True)


# --- Budget vocabulary of the institutional base ----------------------------------------------------------------
PROGRAMS = {
    "01": ("Administración central", "Administración central"),
    "55": ("Sistema de protección especial en el ciclo de vida", "Protección especial"),
    "56": ("Desarrollo infantil", "Desarrollo infantil"),
    "57": ("Protección social a la familia, aseguramiento no contributivo, inclusión económica y movilidad social",
           "Protección social a la familia"),
    "58": ("Servicios de atención gerontológica", "Atención gerontológica"),
    "59": ("Atención integral a personas con discapacidades", "Atención a personas con discapacidad"),
    "61": ("Articulación territorial y participación", "Articulación territorial"),
    "75": ("Coordinación en la formulación, ejecución, seguimiento y evaluación de las políticas públicas",
           "Coordinación de políticas públicas"),
}
SPENDING_GROUPS = {
    "51": "Egresos en personal", "53": "Bienes y servicios de consumo", "57": "Otros egresos corrientes",
    "58": "Transferencias o donaciones corrientes", "71": "Egresos en personal para inversión",
    "73": "Bienes y servicios para inversión", "75": "Obras públicas", "77": "Otros egresos de inversión",
    "78": "Transferencias o donaciones para inversión", "84": "Egresos de capital", "99": "Otros pasivos",
}
FUNDING_SOURCES = {
    "1": "Recursos fiscales", "001": "Recursos fiscales", "202": "Préstamos externos", "301": "Colocaciones internas",
    "701": "Asistencia técnica y donaciones", "998": "Anticipos de ejercicios anteriores",
}


def _code(value: object) -> str:
    text = "" if _missing(value) else str(value).strip()
    return text.zfill(2) if text.isdigit() and len(text) < 2 else text


def budget_program(code: object, raw: object, *, short: bool = False) -> str:
    known = PROGRAMS.get(_code(code))
    if known:
        return known[1] if short else known[0]
    return sentence(raw)


def spending_group(code: object, raw: object) -> str:
    return SPENDING_GROUPS.get(_code(code)) or sentence(raw)


def funding_source(code: object, raw: object) -> str:
    text = "" if _missing(code) else str(code).strip()
    return FUNDING_SOURCES.get(text) or FUNDING_SOURCES.get(text.lstrip("0")) or sentence(raw)


def spending_type(raw: object) -> str:
    text = key(raw)
    if "INVERSION" in text:
        return "Gasto de inversión"
    if "CORRIENTE" in text:
        return "Gasto corriente"
    return sentence(raw)


def zone(raw: object) -> str:
    """``PLANTA CENTRAL`` → ``Planta central``; ``ZONA 5`` → ``Zona 5``."""
    text = key(raw)
    match = re.fullmatch(r"ZONA\s*(\d+)", text)
    if match:
        return f"Zona {int(match[1])}"
    return sentence(raw)


def zone_code(raw: object) -> str | None:
    """Map key of a planning zone (``Z1`` … ``Z9``); the central office has none."""
    match = re.fullmatch(r"ZONA\s*(\d+)", key(raw))
    return f"Z{int(match[1])}" if match else None


# Districts whose source name lists parishes instead of the cantons they serve.
_DISTRICT_PLACES = {"23D01": "Santo Domingo"}


def executing_unit(raw: object) -> str:
    """``DIRECCION DISTRITAL-09D03-GARCIA MORENO a ROCA-MIES`` → ``Dirección Distrital 09D03 – García Moreno a Roca``."""
    if _missing(raw):
        return "—"
    text = " ".join(str(raw).split())
    text = re.sub(r"^\s*MIES\s*-\s*", "", text, flags=re.I)
    text = re.sub(r"\s*-\s*MIES\s*$", "", text, flags=re.I)
    upper = text.upper()
    if "PLANTA CENTRAL" in upper:
        return "Planta central"
    district = re.search(r"DIRECCI[OÓ]N DISTRITAL\W*([O0]?\d{1,2})\s*D\s*(\d{2})(.*)$", upper)
    if district:
        number = f"{int(district[1].replace('O', '0')):02d}D{district[2]}"
        places = district[3].strip(" -")
        if not places or "PARROQUIAS" in places:
            known = _DISTRICT_PLACES.get(number)
            return f"Dirección Distrital {number} – {known}" if known else f"Dirección Distrital {number}"
        towns = [place(t) for t in re.split(r"\s*-+\s*", places) if t.strip()]
        return f"Dirección Distrital {number} – {', '.join(towns)}"
    zonal = re.fullmatch(r"COORDINACI[OÓ]N ZONAL\s*(\d+)", upper.strip())
    if zonal:
        return f"Coordinación Zonal {int(zonal[1])}"
    return place(text, short=False)  # a unit name is a proper noun: Dirección de Transferencia
