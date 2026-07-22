"""
Definición de proveedores de telefonía Argentina y el formato que requieren.
Cada proveedor tiene un campo de salida preferido del resultado del validador,
más un OutputTemplate que define la estructura del CSV de exportación.
"""

from dataclasses import dataclass, field


@dataclass
class OutputTemplate:
    """
    Estructura del CSV de salida para este carrier o discador.

    phone_column  : nombre de la columna que llevará el número formateado
    meta_fields   : campos del PhoneResult a incluir como columnas extra
                    lista de tuplas (atributo, nombre_columna)
    static_fields : columnas con valor fijo (orden importa para el CSV)
                    dict ordenado {nombre_columna: valor_default}
    delimiter     : separador de campos (default coma)
    encoding      : encoding del archivo (default utf-8)
    bom           : agregar BOM UTF-8 (útil para Excel en Windows)
    """
    phone_column: str = "numero"
    meta_fields: list[tuple[str, str]] = field(default_factory=list)
    static_fields: dict[str, str] = field(default_factory=dict)
    delimiter: str = ","
    encoding: str = "utf-8"
    bom: bool = False


# Plantillas reutilizables
_TEMPLATE_SIMPLE = OutputTemplate(
    phone_column="numero",
    meta_fields=[
        ("line_type", "tipo"),
        ("modalidad", "modalidad"),
        ("operador",  "operador"),
        ("provincia", "localidad"),
    ],
)

_TEMPLATE_E164 = OutputTemplate(
    phone_column="numero",
    meta_fields=[
        ("line_type", "tipo"),
        ("modalidad", "modalidad"),
        ("operador",  "operador"),
    ],
)

_TEMPLATE_VICIDIAL = OutputTemplate(
    phone_column="phone_number",
    meta_fields=[],
    static_fields={
        "list_id":         "",
        "first_name":      "",
        "last_name":       "",
        "address1":        "",
        "city":            "",
        "state":           "",
        "province":        "",
        "postal_code":     "",
        "country_code":    "AR",
        "gender":          "",
        "date_of_birth":   "",
        "alt_phone":       "",
        "email":           "",
        "security_phrase": "",
        "comments":        "",
        "status":          "NEW",
        "called_count":    "0",
        "last_local_call_time": "",
        "rank":            "0",
        "owner":           "",
    },
    bom=False,
)

_TEMPLATE_ASTERVOIP = OutputTemplate(
    phone_column="telefono",
    meta_fields=[
        ("line_type", "tipo"),
        ("modalidad", "modalidad"),
        ("operador",  "operador"),
        ("provincia", "localidad"),
    ],
    static_fields={
        "nombre":    "",
        "apellido":  "",
        "campana":   "",
        "agente":    "",
        "extra1":    "",
        "extra2":    "",
    },
)

_TEMPLATE_GOAUTODIAL = OutputTemplate(
    phone_column="phone_number",
    meta_fields=[],
    static_fields={
        "title":        "",
        "first_name":   "",
        "middle_initial": "",
        "last_name":    "",
        "address1":     "",
        "address2":     "",
        "address3":     "",
        "city":         "",
        "state":        "",
        "province":     "",
        "postal_code":  "",
        "country_code": "AR",
        "gender":       "U",
        "date_of_birth": "",
        "alt_phone":    "",
        "email":        "",
        "comments":     "",
        "status":       "",
    },
)


@dataclass
class Provider:
    name: str
    description: str
    landline_format: str         # key de PhoneResult.formats
    mobile_format: str           # key de PhoneResult.formats
    notes: str = ""
    template: OutputTemplate = field(default_factory=lambda: OutputTemplate())


PROVIDERS: dict[str, Provider] = {

    # ── Carriers SIP / trunks ─────────────────────────────────────────────────

    "simvoz": Provider(
        name="Simvoz",
        description="Simvoz / Voxbone SIP trunk",
        landline_format="fmt_e164",
        mobile_format="fmt_e164_movil",
        notes="Móvil requiere +549, fijo +54",
        template=_TEMPLATE_E164,
    ),
    "iplan": Provider(
        name="IPLAN",
        description="IPLAN troncales SIP",
        landline_format="fmt_10dig",
        mobile_format="fmt_10dig",
        notes="10 dígitos sin 0 ni +",
        template=OutputTemplate(
            phone_column="numero",
            meta_fields=[("line_type", "tipo"), ("operador", "operador")],
        ),
    ),
    "claro": Provider(
        name="Claro AR",
        description="Claro Argentina troncal SIP",
        landline_format="fmt_con_0",
        mobile_format="fmt_con_0",
        notes="11 dígitos con 0 inicial",
        template=_TEMPLATE_SIMPLE,
    ),
    "personal": Provider(
        name="Personal (Telecom)",
        description="Personal / Telecom troncal SIP",
        landline_format="fmt_con_0",
        mobile_format="fmt_con_0_15",
        notes="Fijo con 0, móvil con 0+área+15",
        template=_TEMPLATE_SIMPLE,
    ),
    "movistar": Provider(
        name="Movistar AR",
        description="Movistar Argentina troncal SIP",
        landline_format="fmt_con_0",
        mobile_format="fmt_e164_movil",
        notes="Fijo con 0, móvil E.164 con 9",
        template=_TEMPLATE_SIMPLE,
    ),
    "voxbone": Provider(
        name="Voxbone / Bandwidth",
        description="Voxbone / Bandwidth internacional",
        landline_format="fmt_e164",
        mobile_format="fmt_e164_movil",
        notes="E.164 estándar",
        template=_TEMPLATE_E164,
    ),
    "twilio": Provider(
        name="Twilio",
        description="Twilio SIP / REST",
        landline_format="fmt_e164",
        mobile_format="fmt_e164_movil",
        notes="E.164 estándar, móvil con +549",
        template=_TEMPLATE_E164,
    ),
    "voximplant": Provider(
        name="Voximplant",
        description="Voximplant cloud telephony",
        landline_format="fmt_intl",
        mobile_format="fmt_intl_movil",
        notes="Sin +, con código de país",
        template=_TEMPLATE_E164,
    ),
    "netvoip": Provider(
        name="Net2Phone / NetVoip AR",
        description="Net2Phone Argentina",
        landline_format="fmt_e164",
        mobile_format="fmt_e164_movil",
        notes="E.164",
        template=_TEMPLATE_E164,
    ),

    # ── Discadores (dialers) ──────────────────────────────────────────────────

    "astervoip": Provider(
        name="AsterVoIP (discador)",
        description="Discador AsterVoIP — importación de base de contactos",
        landline_format="fmt_con_0",
        mobile_format="fmt_con_0_15",
        notes="Fijo con 0, móvil con 0+área+15. Columnas extra vacías para completar.",
        template=_TEMPLATE_ASTERVOIP,
    ),
    "vicidial": Provider(
        name="Vicidial",
        description="Vicidial / Goautodial — formato de importación de leads",
        landline_format="fmt_con_0",
        mobile_format="fmt_con_0",
        notes="Formato nativo de importación de listas Vicidial",
        template=_TEMPLATE_VICIDIAL,
    ),
    "goautodial": Provider(
        name="GoAutodial",
        description="GoAutodial — formato de importación de contactos",
        landline_format="fmt_con_0",
        mobile_format="fmt_con_0",
        notes="Similar a Vicidial con campos adicionales",
        template=_TEMPLATE_GOAUTODIAL,
    ),
    "issabel": Provider(
        name="Issabel / FreePBX",
        description="Issabel o FreePBX con trunk genérico",
        landline_format="fmt_con_0",
        mobile_format="fmt_con_0",
        notes="11 dígitos con 0",
        template=_TEMPLATE_SIMPLE,
    ),

    # ── Genéricos ─────────────────────────────────────────────────────────────

    "asterisk_local": Provider(
        name="Asterisk local (genérico)",
        description="Dialplan Asterisk sin trunk específico",
        landline_format="fmt_asterisk",
        mobile_format="fmt_asterisk",
        notes="10 dígitos, el dialplan agrega 0 o lo que necesite",
        template=OutputTemplate(phone_column="numero"),
    ),
    "generico_10": Provider(
        name="Genérico 10 dígitos",
        description="Proveedores que piden 10 dígitos sin nada",
        landline_format="fmt_10dig",
        mobile_format="fmt_10dig",
        template=OutputTemplate(phone_column="numero"),
    ),
    "generico_e164": Provider(
        name="Genérico E.164",
        description="Proveedores que piden E.164 estándar con +549 para móvil",
        landline_format="fmt_e164",
        mobile_format="fmt_e164_movil",
        template=_TEMPLATE_E164,
    ),
}


def list_providers() -> list[str]:
    return list(PROVIDERS.keys())


def get_provider(key: str) -> Provider | None:
    return PROVIDERS.get(key.lower())


def format_for_provider(formats: dict, line_type: str, provider_key: str) -> str | None:
    provider = get_provider(provider_key)
    if not provider:
        return None
    fmt_key = provider.mobile_format if line_type == "mobile" else provider.landline_format
    return formats.get(fmt_key)
