"""
Plan Nacional de Numeración Argentina (PNN) - ENACOM.
Fuente: https://www.enacom.gob.ar/numeracion_p5.html
Rangos de numeración para identificar fijo vs móvil.

Estructura del número argentino normalizado (10 dígitos, sin 0 ni +54):
  [AREA][ABONADO]
  donde AREA puede ser 2, 3 o 4 dígitos y AREA+ABONADO = 10 dígitos.

Móvil en E.164: +54 9 [AREA][ABONADO]   → el 9 distingue móvil de fijo
Fijo  en E.164: +54   [AREA][ABONADO]
"""

from dataclasses import dataclass, field


@dataclass
class AreaInfo:
    code: str
    digits: int          # dígitos del área (2, 3 o 4)
    subscriber_len: int  # dígitos del abonado (10 - digits)
    province: str
    city: str = ""
    # Prefijos del abonado que son MÓVIL (primeros 1-2 dígitos del subscriber)
    # Si está vacío, se usa el flag has_mobile_range para indicar rangos conocidos
    mobile_sub_prefixes: list[str] = field(default_factory=list)
    # Prefijos del abonado que son FIJO
    landline_sub_prefixes: list[str] = field(default_factory=list)


# ─── Áreas de 2 dígitos (área 11 - AMBA) ─────────────────────────────────────
# En el área 11, el abonado tiene 8 dígitos.
# Post-reforma 2011: móviles tienen abonado 1XXXXXXX (eran "15-XXXXXXX")
# Fijos: 4XXXXXXX, 5XXXXXXX, 6XXXXXXX, 3XXXXXXX (algunos)
# VOIP/nuevos: 5XXXXXXX pueden ser fijo o móvil (Ej: WhatsApp, Zoom numbers)
AREA_11 = AreaInfo(
    code="11", digits=2, subscriber_len=8,
    province="Buenos Aires (AMBA)",
    city="Ciudad de Buenos Aires / Gran Buenos Aires",
    mobile_sub_prefixes=["2", "3", "6", "7", "8", "9"],
    # Nota: 1 puede ser móvil o fijo (fijos legacy), 4/5 generalmente fijo
    landline_sub_prefixes=["4", "5"],
)

# ─── Áreas de 3 dígitos ───────────────────────────────────────────────────────
AREAS_3: dict[str, AreaInfo] = {
    "220": AreaInfo("220", 3, 7, "Buenos Aires", "Junín"),
    "221": AreaInfo("221", 3, 7, "Buenos Aires", "La Plata",
                    mobile_sub_prefixes=["4", "5", "6"],
                    landline_sub_prefixes=["4", "2", "3"]),
    "223": AreaInfo("223", 3, 7, "Buenos Aires", "Mar del Plata",
                    mobile_sub_prefixes=["5", "6"],
                    landline_sub_prefixes=["4", "4"]),
    "230": AreaInfo("230", 3, 7, "Buenos Aires", "Mercedes"),
    "236": AreaInfo("236", 3, 7, "Buenos Aires", "Olavarría"),
    "237": AreaInfo("237", 3, 7, "Buenos Aires", "Moreno/Merlo"),
    "249": AreaInfo("249", 3, 7, "Buenos Aires", "Tandil"),
    "260": AreaInfo("260", 3, 7, "Mendoza", "San Rafael"),
    "261": AreaInfo("261", 3, 7, "Mendoza", "Mendoza capital",
                    mobile_sub_prefixes=["5", "6"],
                    landline_sub_prefixes=["4"]),
    "263": AreaInfo("263", 3, 7, "San Juan", "San Martín"),
    "264": AreaInfo("264", 3, 7, "San Juan", "San Juan capital",
                    mobile_sub_prefixes=["5"],
                    landline_sub_prefixes=["4"]),
    "266": AreaInfo("266", 3, 7, "San Luis", "San Luis capital"),
    "280": AreaInfo("280", 3, 7, "Chubut", "Rawson"),
    "291": AreaInfo("291", 3, 7, "Buenos Aires", "Bahía Blanca",
                    mobile_sub_prefixes=["5"],
                    landline_sub_prefixes=["4"]),
    "294": AreaInfo("294", 3, 7, "Río Negro/Neuquén", "Bariloche"),
    "296": AreaInfo("296", 3, 7, "Chubut", "Comodoro Rivadavia"),
    "297": AreaInfo("297", 3, 7, "Chubut", "Comodoro Rivadavia",
                    mobile_sub_prefixes=["4", "5"],
                    landline_sub_prefixes=["4"]),
    "298": AreaInfo("298", 3, 7, "Neuquén", "Neuquén capital"),
    "299": AreaInfo("299", 3, 7, "Neuquén", "Neuquén capital",
                    mobile_sub_prefixes=["4", "5"],
                    landline_sub_prefixes=["4"]),
    "341": AreaInfo("341", 3, 7, "Santa Fe", "Rosario",
                    mobile_sub_prefixes=["5", "6"],
                    landline_sub_prefixes=["4", "4"]),
    "342": AreaInfo("342", 3, 7, "Santa Fe", "Santa Fe capital",
                    mobile_sub_prefixes=["5"],
                    landline_sub_prefixes=["4"]),
    "343": AreaInfo("343", 3, 7, "Entre Ríos", "Paraná"),
    "345": AreaInfo("345", 3, 7, "Entre Ríos", "Concordia"),
    "346": AreaInfo("346", 3, 7, "Entre Ríos", "Gualeguaychú"),
    "348": AreaInfo("348", 3, 7, "Buenos Aires", "Pergamino"),
    "351": AreaInfo("351", 3, 7, "Córdoba", "Córdoba capital",
                    mobile_sub_prefixes=["5", "6"],
                    landline_sub_prefixes=["4"]),
    "353": AreaInfo("353", 3, 7, "Córdoba", "Villa María"),
    "354": AreaInfo("354", 3, 7, "Córdoba", "Río Cuarto"),
    "357": AreaInfo("357", 3, 7, "Córdoba", "Río Cuarto"),
    "358": AreaInfo("358", 3, 7, "Córdoba", "Río Cuarto"),
    "362": AreaInfo("362", 3, 7, "Chaco", "Resistencia"),
    "364": AreaInfo("364", 3, 7, "Formosa", "Formosa capital"),
    "370": AreaInfo("370", 3, 7, "Misiones", "Posadas"),
    "376": AreaInfo("376", 3, 7, "Misiones", "Posadas"),
    "379": AreaInfo("379", 3, 7, "Corrientes", "Corrientes capital"),
    "380": AreaInfo("380", 3, 7, "La Rioja", "La Rioja capital"),
    "381": AreaInfo("381", 3, 7, "Tucumán", "Tucumán capital",
                    mobile_sub_prefixes=["5"],
                    landline_sub_prefixes=["4"]),
    "383": AreaInfo("383", 3, 7, "Catamarca", "Catamarca capital"),
    "385": AreaInfo("385", 3, 7, "Santiago del Estero", "Stgo. del Estero"),
    "387": AreaInfo("387", 3, 7, "Salta", "Salta capital",
                    mobile_sub_prefixes=["4", "5"],
                    landline_sub_prefixes=["4"]),
    "388": AreaInfo("388", 3, 7, "Jujuy", "San Salvador de Jujuy"),
    "421": AreaInfo("421", 3, 7, "Entre Ríos", "Nogoyá"),
    "423": AreaInfo("423", 3, 7, "Buenos Aires", "Mar del Plata (alt)"),
    "472": AreaInfo("472", 3, 7, "Córdoba", "Jesús María"),
    "810": AreaInfo("810", 3, 7, "Nacional", "Números 0810 (pago por llamante)"),
    "800": AreaInfo("800", 3, 7, "Nacional", "Números 0800 (gratuito)"),
}

# ─── Lookup unificado ─────────────────────────────────────────────────────────

def get_area_info(national_10: str) -> AreaInfo | None:
    """Dado el número de 10 dígitos, retorna la info del área."""
    if national_10[:2] == "11":
        return AREA_11
    code3 = national_10[:3]
    if code3 in AREAS_3:
        return AREAS_3[code3]
    # Área de 4 dígitos: retorno genérico
    return AreaInfo(
        code=national_10[:4], digits=4, subscriber_len=6,
        province="Argentina",
        city="Interior (área 4 dígitos)"
    )


def classify_line_type(national_10: str, hint: str | None = None) -> str:
    """
    Clasifica el número como 'mobile', 'landline' o 'unknown'.

    hint puede ser:
      'mobile'   → el número vino con "+549" o con "15" explícito
      'landline' → el número vino con "+54" (sin 9) en formato E.164
      None       → sin información extra, usar heurísticas
    """
    if hint == "mobile":
        return "mobile"
    if hint == "landline":
        return "landline"

    info = get_area_info(national_10)
    if info is None:
        return "unknown"

    subscriber = national_10[info.digits:]
    first_digit = subscriber[0] if subscriber else ""

    if first_digit in info.mobile_sub_prefixes and first_digit not in info.landline_sub_prefixes:
        return "mobile"
    if first_digit in info.landline_sub_prefixes and first_digit not in info.mobile_sub_prefixes:
        return "landline"

    # Ambiguo: en Argentina post-reforma, prefijos 1-3 del abonado
    # suelen ser móvil (eran "15-xxx"), 4-6 suelen ser fijo
    if first_digit in ("1", "2", "3"):
        return "mobile"
    if first_digit in ("4", "5", "6"):
        return "landline"

    return "unknown"
