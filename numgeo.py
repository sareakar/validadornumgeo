"""
Lookup de numeración geográfica ENACOM.
Fuente: "Numeración Geográfica.xls" descargado de enacom.gob.ar

Estructura del CSV:
  OPERADOR, SERVICIO, MODALIDAD, LOCALIDAD, INDICATIVO, BLOQUE, RESOLUCION, FECHA

Lookup: (INDICATIVO, LEFT(abonado, len(BLOQUE))) → fila

Modalidad → tipo de línea:
  BASICA → landline
  CPP    → mobile  (Calling Party Pays)
  MPP    → mobile  (Mobile Party Pays)
"""

import csv
import os
from dataclasses import dataclass

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "numgeo_enacom.csv")

_MOBILE_MODALITIES = {"CPP", "MPP"}
_LANDLINE_MODALITIES = {"BASICA"}


@dataclass(frozen=True)
class NumgeoRecord:
    operador: str
    servicio: str
    modalidad: str
    localidad: str
    indicativo: str
    bloque: str

    @property
    def line_type(self) -> str:
        if self.modalidad in _MOBILE_MODALITIES:
            return "mobile"
        if self.modalidad in _LANDLINE_MODALITIES:
            return "landline"
        return "unknown"

    @property
    def operator_short(self) -> str:
        """Nombre corto del operador para mostrar en tablas."""
        name = self.operador
        # Simplificar nombres comunes
        replacements = [
            ("TELEFONICA DE ARGENTINA S.A.", "Telecom (ex-Telefónica)"),
            ("TELEFONICA MOVILES ARGENTINA", "Movistar"),
            ("TELECOM ARGENTINA", "Telecom"),
            ("TELECOM PERSONAL", "Personal"),
            ("AMX ARGENTINA", "Claro"),
            ("CTI ", "Claro (ex-CTI)"),
            ("NEXTEL", "Nextel"),
            ("CLARO", "Claro"),
        ]
        for pattern, short in replacements:
            if pattern in name.upper():
                return short
        # Recortar nombres muy largos
        if len(name) > 35:
            name = name[:33] + "…"
        return name


# ─── Índice en memoria ────────────────────────────────────────────────────────
# _index[(indicativo, bloque_str)] = NumgeoRecord
_index: dict[tuple[str, str], NumgeoRecord] = {}
_loaded = False


def _load():
    global _loaded
    if _loaded:
        return
    if not os.path.exists(_DATA_FILE):
        return

    with open(_DATA_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            indicativo = str(row["INDICATIVO"]).strip()
            bloque = str(row["BLOQUE"]).strip()
            if not indicativo or not bloque:
                continue
            rec = NumgeoRecord(
                operador=row["OPERADOR"].strip(),
                servicio=row["SERVICIO"].strip(),
                modalidad=row["MODALIDAD"].strip(),
                localidad=row["LOCALIDAD"].strip(),
                indicativo=indicativo,
                bloque=bloque,
            )
            key = (indicativo, bloque)
            # Si ya existe una entrada más específica (mismo indicativo+bloque)
            # que sea BASICA, no pisarla con una CPP del mismo bloque
            if key not in _index:
                _index[key] = rec

    _loaded = True


def lookup(indicativo: str, subscriber: str) -> NumgeoRecord | None:
    """
    Busca el bloque más específico (prefijo más largo) que coincida
    con el comienzo del número de abonado.
    """
    _load()
    if not _index:
        return None

    # Probar desde el prefijo más largo al más corto (5 → 4 → 3 → 2)
    for length in (5, 4, 3, 2):
        prefix = subscriber[:length]
        rec = _index.get((indicativo, prefix))
        if rec:
            return rec

    return None


def is_loaded() -> bool:
    _load()
    return bool(_index)


def stats() -> dict:
    _load()
    total = len(_index)
    mobile = sum(1 for r in _index.values() if r.line_type == "mobile")
    landline = sum(1 for r in _index.values() if r.line_type == "landline")
    indicativos = len({k[0] for k in _index})
    return {
        "total_bloques": total,
        "movil": mobile,
        "fijo": landline,
        "indicativos": indicativos,
    }
