"""
Validador de números telefónicos argentinos.
Sin dependencias externas — usa el Plan Nacional de Numeración (PNN/ENACOM).

Árbol de decisión:

  PASO 1 — Limpieza: quitar separadores, prefijos de país, 0 troncal.

  PASO 2 — Geografía (AMBA vs Interior):
    8 dígitos               → AMBA  (área 11 es la única con abonados de 8 dig en AR)
    10 dig, empieza con 11  → AMBA  (ya tiene área)
    10 dig, empieza con 15  → AMBA móvil (15 = prefijo CPP sin área, prepende 11)
    resto                   → Interior

  PASO 3 — Completar a 10 dígitos:
    AMBA 8 dig  → prepende "11"
    AMBA 15+8   → quita "15", prepende "11", hint=mobile
    Interior    → parsear área 3 o 4 dígitos normalmente

  PASO 4 — Lookup ENACOM → modalidad (CPP / MPP / BASICA) + operador + localidad

  PASO 5 — Generar todos los formatos de salida
"""

import re
from ar_numbering import get_area_info, classify_line_type
import numgeo as _numgeo

try:
    import phonenumbers as _pn
    _HAS_PHONENUMBERS = True
except ImportError:
    _HAS_PHONENUMBERS = False


_AREA2 = {"11"}
_AREA3 = {
    "220", "221", "223", "230", "236", "237", "249",
    "260", "261", "263", "264", "266", "280",
    "291", "294", "296", "297", "298", "299",
    "341", "342", "343", "345", "346", "348",
    "351", "353", "354", "357", "358",
    "362", "364", "370", "376", "379",
    "380", "381", "383", "385", "387", "388",
    "421", "423", "472",
    "800", "810",
}


# ─── Resultado ────────────────────────────────────────────────────────────────

class PhoneResult:
    def __init__(self, original: str):
        self.original    = original
        self.valid       = False
        self.geografia   : str | None = None   # "AMBA" | "Interior"
        self.line_type   : str | None = None   # "mobile" | "landline" | "unknown"
        self.area_code   : str | None = None
        self.subscriber  : str | None = None
        self.province    : str | None = None
        self.city        : str | None = None
        self.operador    : str | None = None
        self.servicio    : str | None = None
        self.modalidad   : str | None = None   # "BASICA" | "CPP" | "MPP"
        self.formats     : dict = {}
        self.source      : str = "heuristica"  # "hint"|"enacom_db"|"heuristica"
        self.repaired    : bool = False
        self.repair_note : str | None = None
        self.error       : str | None = None

    def to_dict(self) -> dict:
        d = {
            "original":         self.original,
            "valido":           "SI" if self.valid else "NO",
            "geografia":        self.geografia or "",
            "tipo":             self.line_type or "",
            "modalidad":        self.modalidad or "",
            "area":             self.area_code or "",
            "abonado":          self.subscriber or "",
            "provincia":        self.province or "",
            "ciudad":           self.city or "",
            "operador":         self.operador or "",
            "servicio":         self.servicio or "",
            "fuente":           self.source,
            "reparado":         "SI" if self.repaired else "",
            "nota_reparacion":  self.repair_note or "",
            "error":            self.error or "",
        }
        d.update(self.formats)
        return d


# ─── PASO 1: Limpieza ─────────────────────────────────────────────────────────

def _strip(number: str) -> str:
    return re.sub(r"[\s\-\.\(\)/]", "", number.strip())


def _remove_intl_prefix(n: str) -> tuple[str, str | None]:
    """
    Quita prefijos de país y troncal.
    Retorna (número_limpio, hint) donde hint in ('mobile', None).

    Reglas E.164 / WhatsApp para Argentina:
      +549XXXXXXXXXX  → móvil (hint=mobile)   — el 9 es indicador de móvil en ITU
      +54XXXXXXXXXX   → sin hint               — puede ser fijo O móvil guardado sin 9
      549XXXXXXXXXX   → móvil (hint=mobile)    — sin +, mismo criterio
      54XXXXXXXXXX    → sin hint               — ENACOM decide
      0054[9]XX...    → ídem con 0054
    """
    hint = None

    if n.startswith("+"):
        if n.startswith("+549"):   n, hint = n[4:], "mobile"
        elif n.startswith("+54"):  n = n[3:]          # no hint — ENACOM decide
        else:                      return "", None     # otro país

    elif n.startswith("0054"):
        n = n[4:]
        if n.startswith("9"):  n, hint = n[1:], "mobile"

    elif n.startswith("549"):
        # 549 + 10 dígitos = 13 chars  →  móvil
        # 549 + algo más corto: quitar 549 y dejar que el árbol maneje
        if len(n) >= 13:
            n, hint = n[3:], "mobile"
        else:
            n = n[3:]   # sin hint, puede ser interior incompleto

    elif n.startswith("54"):
        # 54 + 10 dígitos = 12 chars, sin hint
        if len(n) >= 12:
            n = n[2:]
        # 11 chars = 54 + 9 dígitos → podría ser interior incompleto → quitar 54
        elif len(n) == 11:
            n = n[2:]

    if n.startswith("0"):
        n = n[1:]

    return n, hint


def _remove_15(n: str) -> tuple[str, bool]:
    """Elimina el '15' de móvil cuando ya está dentro del número con área."""
    if n[:2] in _AREA2 and len(n) == 12 and n[2:4] == "15":
        return n[:2] + n[4:], True
    if n[:3] in _AREA3 and len(n) == 12 and n[3:5] == "15":
        return n[:3] + n[5:], True
    if len(n) == 12 and n[4:6] == "15":
        return n[:4] + n[6:], True
    return n, False


# ─── PASO 2+3: Geografía y completado ────────────────────────────────────────

def _classify_and_complete(n: str, hint: str | None, default_area: str | None = None
                           ) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Clasifica el número limpio (sin prefijos de país) en AMBA o Interior
    y lo completa a 10 dígitos si hace falta.

    Retorna (national_10, geografia, hint_actualizado, repair_note)
    o (None, None, None, error_msg) si no se puede resolver.
    """
    length = len(n)

    # ── AMBA — 8 dígitos: única zona con abonados de 8 dig en AR ─
    if length == 8:
        return f"11{n}", "AMBA", hint, \
               "área 11 (AMBA) — único área con abonados de 8 dígitos en AR"

    # ── AMBA — 10 dígitos empezando con 15 (CPP sin área) ────────
    # "15XXXXXXXX" = prefijo de móvil BA + 8 dígitos de abonado
    if length == 10 and n.startswith("15"):
        return f"11{n[2:]}", "AMBA", "mobile", \
               "prefijo '15' de móvil AMBA sin área — se asume área 11"

    # ── 12 dígitos — variantes con prefijo 15 o área redundante ──
    #
    # Formas posibles en bases de datos argentinas:
    #   1115XXXXXXXX → 11 + 15 + 8dig  (AMBA — "área luego 15")
    #   1511XXXXXXXX → 15 + 11 + 8dig  (AMBA — "15 luego área")
    #   351156551221 → área3 + 15 + 7dig (Interior — "área luego 15")  ← _remove_15
    #   153516551221 → 15 + área3 + 7dig (Interior — "15 luego área")  ← nuevo
    #   22331655122X → área4 + 15 + 6dig (Interior — "área luego 15")  ← _remove_15
    #   1522336551XX → 15 + área4 + 6dig (Interior — "15 luego área")  ← nuevo
    if length == 12:
        if n.startswith("1115"):        # 11 + 15 + 8dig  (AMBA)
            return f"11{n[4:]}", "AMBA", "mobile", \
                   "formato '11-15-XXXXXXXX' normalizado a 10 dígitos AMBA"
        if n.startswith("1511"):        # 15 + 11 + 8dig  (AMBA)
            return f"11{n[4:]}", "AMBA", "mobile", \
                   "formato '15-11-XXXXXXXX' normalizado a 10 dígitos AMBA"
        if n.startswith("11"):          # 11 + 10dig (área 11 duplicada)
            inner, geo2, hint2, note2 = _classify_and_complete(n[2:], hint, default_area)
            if inner:
                return inner, geo2, hint2, (note2 or "prefijo '11' extra eliminado")
        # Interior: [área]15[sub] → _remove_15 quita el 15 del medio
        n2, had_15 = _remove_15(n)
        if had_15:
            return _classify_and_complete(n2, "mobile", default_area)
        # Interior: 15[área][sub] → el 15 viene ANTES del código de área
        # Ej: 15-351-6551221 → n[2:] = 3516551221 (10 dig nacional)
        # Nota: "1511..." ya fue capturado arriba → aquí inner no empieza con "11"
        if n.startswith("15"):
            inner = n[2:]   # 10 dígitos: [área][abonado]
            area_det = inner[:3] if inner[:3] in _AREA3 else inner[:4]
            return inner, "Interior", "mobile", \
                   f"prefijo '15' de móvil interior eliminado, área {area_det}"
        return None, None, None, f"12 dígitos con formato no reconocido: {n}"

    # ── Formato nacional completo (10 dígitos) ────────────────────
    if length == 10:
        # Eliminar "15" interior si corresponde
        n2, had_15 = _remove_15(n)
        if had_15:
            hint = "mobile"
            n = n2

        if not re.fullmatch(r"\d{10}", n):
            return None, None, None, "longitud incorrecta tras quitar 15"

        geo = "AMBA" if n.startswith("11") else "Interior"
        return n, geo, hint, None

    # ── Con "0" troncal que no se quitó (11 dígitos) ─────────────
    if length == 11 and n.startswith("0"):
        return _classify_and_complete(n[1:], hint, default_area)

    # ── Interior — 7 dígitos (área 3 dig) ────────────────────────
    if length == 7:
        if default_area and len(default_area) == 3 and default_area in _AREA3:
            return f"{default_area}{n}", "Interior", hint, \
                   f"área {default_area} asumida — número de 7 dígitos"
        return None, None, None, \
               "7 dígitos sin área — especificar --default-area (ej: 351 para Córdoba)"

    # ── Interior — 6 dígitos (área 4 dig) ────────────────────────
    if length == 6:
        if default_area and len(default_area) == 4:
            return f"{default_area}{n}", "Interior", hint, \
                   f"área {default_area} asumida — número de 6 dígitos"
        return None, None, None, \
               "6 dígitos sin área — especificar --default-area de 4 dígitos"

    # ── 9 dígitos: caso "9"+8dig móvil BA sin + ni 54 ────────────
    if length == 9 and n.startswith("9") and not n[1:3] in _AREA3:
        return f"11{n[1:]}", "AMBA", "mobile", \
               "prefijo '9' de móvil eliminado, área 11 asumida"

    # ── 9 dígitos: "15" + 7 dígitos (móvil interior sin área) ────
    if length == 9 and n.startswith("15"):
        sub7 = n[2:]
        if default_area and len(default_area) == 3 and default_area in _AREA3:
            return f"{default_area}{sub7}", "Interior", "mobile", \
                   f"'15' eliminado, área {default_area} asumida"
        return None, None, None, \
               "9 dígitos con '15' — especificar --default-area de 3 dígitos"

    return None, None, None, f"longitud {length} no reconocida"


# ─── Parser principal ─────────────────────────────────────────────────────────

def _parse_raw(raw: str, default_area: str | None = None
               ) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Retorna (national_10, geografia, hint, repair_note).
    En caso de error: (None, None, None, mensaje_error).
    """
    n = _strip(raw)
    if not n or not re.fullmatch(r"\+?\d+", n):
        return None, None, None, None

    n, hint = _remove_intl_prefix(n)
    if not n:
        return None, None, None, "código de país no reconocido"

    return _classify_and_complete(n, hint, default_area)


# ─── PASO 4: Validación con phonenumbers (opcional) ──────────────────────────

def _validate_with_phonenumbers(n10: str) -> tuple[bool, str | None]:
    if not _HAS_PHONENUMBERS:
        return True, None
    try:
        pn = _pn.parse(f"+54{n10}", None)
        if not _pn.is_valid_number(pn):
            return False, None
        num_type = _pn.number_type(pn)
        from phonenumbers import PhoneNumberType
        if num_type in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE):
            return True, "mobile"
        if num_type == PhoneNumberType.FIXED_LINE:
            return True, "landline"
        return True, "unknown"
    except Exception:
        return False, None


# ─── PASO 5: Formatos de salida ───────────────────────────────────────────────

def _detect_area(n10: str) -> tuple[str, str]:
    if n10[:2] in _AREA2:
        return n10[:2], n10[2:]
    if n10[:3] in _AREA3:
        return n10[:3], n10[3:]
    return n10[:4], n10[4:]


def _build_formats(n10: str, area: str, subscriber: str, line_type: str) -> dict:
    is_mobile = line_type == "mobile"
    return {
        "fmt_10dig":      n10,
        "fmt_con_0":      f"0{n10}",
        "fmt_con_0_15":   f"0{area}15{subscriber}" if is_mobile else f"0{n10}",
        "fmt_con_9":      f"9{n10}" if is_mobile else n10,
        "fmt_e164":       f"+54{n10}",
        "fmt_e164_movil": f"+549{n10}" if is_mobile else f"+54{n10}",
        "fmt_intl":       f"54{n10}",
        "fmt_intl_movil": f"549{n10}" if is_mobile else f"54{n10}",
        "fmt_asterisk":   n10,
    }


# ─── Punto de entrada público ─────────────────────────────────────────────────

def validate(raw: str, default_area: str | None = None) -> PhoneResult:
    result = PhoneResult(raw)

    n10, geografia, hint, repair_note = _parse_raw(raw, default_area)

    if n10 is None:
        result.error = repair_note or "formato_invalido"
        return result

    if repair_note:
        result.repaired = True
        result.repair_note = repair_note

    pn_valid, pn_type = _validate_with_phonenumbers(n10)
    if not pn_valid:
        result.error = "numero_invalido"
        return result

    area, subscriber = _detect_area(n10)

    # Desambiguación 3-dígitos vs 4-dígitos:
    # Si el área de 3 dig no tiene cobertura en ENACOM, probar con 4 dig.
    # Ej: 3832414526 → _detect_area da (383, 2414526) pero ENACOM tiene (3832, 414526).
    ng_rec = _numgeo.lookup(area, subscriber)
    if ng_rec is None and len(area) == 3:
        alt_rec = _numgeo.lookup(n10[:4], n10[4:])
        if alt_rec is not None:
            area, subscriber = n10[:4], n10[4:]
            ng_rec = alt_rec

    area_info = get_area_info(n10)

    if hint:
        line_type = hint
        source    = "hint"
        operador  = ng_rec.operator_short if ng_rec else None
        servicio  = ng_rec.servicio        if ng_rec else None
        modalidad = ng_rec.modalidad       if ng_rec else None
        localidad = ng_rec.localidad       if ng_rec else None
    elif ng_rec:
        line_type = ng_rec.line_type
        operador  = ng_rec.operator_short
        servicio  = ng_rec.servicio
        modalidad = ng_rec.modalidad
        localidad = ng_rec.localidad
        source    = "enacom_db"
    else:
        line_type = classify_line_type(n10, pn_type)
        operador  = None
        servicio  = None
        modalidad = None
        localidad = None
        source    = "heuristica"

    result.valid      = True
    result.geografia  = geografia
    result.area_code  = area
    result.subscriber = subscriber
    result.line_type  = line_type
    result.operador   = operador
    result.servicio   = servicio
    result.modalidad  = modalidad
    result.province   = localidad or (area_info.province if area_info else "Argentina")
    result.city       = area_info.city if area_info else ""
    result.source     = source
    result.formats    = _build_formats(n10, area, subscriber, line_type)

    return result


def validate_bulk(numbers: list[str], default_area: str | None = None) -> list[PhoneResult]:
    return [validate(n, default_area) for n in numbers]
