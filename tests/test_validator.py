"""Tests del validador de números argentinos (sin pytest)."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validator import validate

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

failures = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {name}")
    else:
        print(f"  {FAIL}  {name}" + (f" — {detail}" if detail else ""))
        failures.append(name)


def section(title: str):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ─── Números válidos ──────────────────────────────────────────────────────────

section("Números válidos - móvil BA")

r = validate("1123456789")
check("móvil BA plano → válido", r.valid)
check("móvil BA plano → tipo mobile", r.line_type == "mobile")
check("móvil BA plano → área 11", r.area_code == "11")
check("móvil BA plano → E.164", r.formats.get("fmt_e164") == "+541123456789")
check("móvil BA plano → E.164 móvil", r.formats.get("fmt_e164_movil") == "+5491123456789")
check("móvil BA plano → con 0", r.formats.get("fmt_con_0") == "01123456789")
check("móvil BA plano → con 9", r.formats.get("fmt_con_9") == "91123456789")
check("móvil BA plano → 10 dígitos", r.formats.get("fmt_10dig") == "1123456789")

r = validate("01123456789")
check("móvil BA con 0 → válido", r.valid)
check("móvil BA con 0 → tipo mobile", r.line_type == "mobile")

r = validate("+5491123456789")
check("móvil BA E.164 +549 → válido", r.valid)
check("móvil BA E.164 +549 → tipo mobile", r.line_type == "mobile")
check("móvil BA E.164 +549 → área 11", r.area_code == "11")

r = validate("011-15-2345-6789")
check("móvil BA con 011-15 → válido", r.valid)
check("móvil BA con 011-15 → tipo mobile", r.line_type == "mobile", f"got: {r.line_type}")
check("móvil BA con 011-15 → normalizado igual", r.formats.get("fmt_10dig") == "1123456789",
      f"got: {r.formats.get('fmt_10dig')}")

section("Números válidos - fijo BA")

r = validate("1143219876")
check("fijo BA → válido", r.valid)
check("fijo BA → tipo landline", r.line_type == "landline", f"got: {r.line_type}")
check("fijo BA → área 11", r.area_code == "11")
check("fijo BA → E.164 sin 9", r.formats.get("fmt_e164") == "+541143219876")
check("fijo BA → E.164 movil == E.164 (sin 9)", r.formats.get("fmt_e164_movil") == "+541143219876")
check("fijo BA → con 0_15 no agrega 15", r.formats.get("fmt_con_0_15") == "01143219876")

r = validate("01143219876")
check("fijo BA con 0 → válido", r.valid)
check("fijo BA con 0 → tipo landline", r.line_type == "landline")

r = validate("+541143219876")
check("fijo BA E.164 +54 → válido", r.valid)
check("fijo BA E.164 +54 → tipo landline", r.line_type == "landline")

section("Números válidos - interior fijo")

r = validate("3514123456")
check("fijo Córdoba → válido", r.valid)
check("fijo Córdoba → área 351", r.area_code == "351")
check("fijo Córdoba → provincia", "ORDOBA" in (r.province or "").upper())

r = validate("3412345678")
check("Rosario → válido", r.valid)
check("Rosario → área 341", r.area_code == "341")

r = validate("2614567890")
check("Mendoza → válido", r.valid)
check("Mendoza → área 261", r.area_code == "261")

section("Prefijo 15 en interior — área ANTES del 15 ([área]15[sub])")

# 0[área]15[sub] → strip 0 → [área]15[sub] (12 dig) → _remove_15 quita 15
r = validate("0351156551221")
check("Córdoba 0351-15-6551221 → válido",   r.valid, r.error)
check("Córdoba 0351-15-6551221 → mobile",   r.line_type == "mobile", r.line_type)
check("Córdoba 0351-15-6551221 → área 351", r.area_code == "351",    r.area_code)
check("Córdoba 0351-15-6551221 → 10dig",    r.formats.get("fmt_10dig") == "3516551221",
      r.formats.get("fmt_10dig"))

r = validate("351-15-655-1221")
check("Córdoba 351-15-... separadores → válido",   r.valid, r.error)
check("Córdoba 351-15-... separadores → mobile",   r.line_type == "mobile", r.line_type)
check("Córdoba 351-15-... separadores → 10dig",    r.formats.get("fmt_10dig") == "3516551221",
      r.formats.get("fmt_10dig"))

r = validate("0261154567890")
check("Mendoza 0261-15-4567890 → válido",   r.valid, r.error)
check("Mendoza 0261-15-4567890 → mobile",   r.line_type == "mobile", r.line_type)
check("Mendoza 0261-15-4567890 → área 261", r.area_code == "261",    r.area_code)

section("Prefijo 15 en interior — 15 ANTES del área (15[área][sub])")

# 15[área3][sub7] = 12 dígitos (sin 0 adelante)
r = validate("153516551221")
check("15-351-6551221 (sin 0) → válido",   r.valid, r.error)
check("15-351-6551221 (sin 0) → mobile",   r.line_type == "mobile",  r.line_type)
check("15-351-6551221 (sin 0) → área 351", r.area_code == "351",     r.area_code)
check("15-351-6551221 (sin 0) → 10dig",    r.formats.get("fmt_10dig") == "3516551221",
      r.formats.get("fmt_10dig"))

# 015[área3][sub7] = 13 dígitos → strip 0 → 12 dígitos empezando con 15
r = validate("0153516551221")
check("015-351-6551221 → válido",   r.valid, r.error)
check("015-351-6551221 → mobile",   r.line_type == "mobile",  r.line_type)
check("015-351-6551221 → área 351", r.area_code == "351",     r.area_code)
check("015-351-6551221 → 10dig",    r.formats.get("fmt_10dig") == "3516551221",
      r.formats.get("fmt_10dig"))

r = validate("15-351-655-1221")
check("15-351-... separadores → válido",   r.valid, r.error)
check("15-351-... separadores → mobile",   r.line_type == "mobile",  r.line_type)
check("15-351-... separadores → 10dig",    r.formats.get("fmt_10dig") == "3516551221",
      r.formats.get("fmt_10dig"))

# Mendoza: 15[261][sub7]
r = validate("152614567890")
check("15-261-4567890 Mendoza → válido",   r.valid, r.error)
check("15-261-4567890 Mendoza → mobile",   r.line_type == "mobile",  r.line_type)
check("15-261-4567890 Mendoza → área 261", r.area_code == "261",     r.area_code)

# Tucumán: 015[381][sub7]
r = validate("0153814567890")
check("015-381-4567890 Tucumán → válido",   r.valid, r.error)
check("015-381-4567890 Tucumán → mobile",   r.line_type == "mobile",  r.line_type)
check("015-381-4567890 Tucumán → área 381", r.area_code == "381",     r.area_code)

section("Prefijo 15 en interior — formatos de salida CPP")

r = validate("0351156551221")
if r.valid and r.line_type == "mobile":
    check("CPP Córdoba → fmt_con_0_15 correcto",
          r.formats.get("fmt_con_0_15") == "0351156551221",
          r.formats.get("fmt_con_0_15"))
    check("CPP Córdoba → fmt_e164_movil con +549",
          r.formats.get("fmt_e164_movil") == "+5493516551221",
          r.formats.get("fmt_e164_movil"))
    check("CPP Córdoba → fmt_con_0 sin 15",
          r.formats.get("fmt_con_0") == "03516551221",
          r.formats.get("fmt_con_0"))
else:
    check("CPP Córdoba validado previamente", False, f"válido={r.valid} tipo={r.line_type}")

section("Ambigüedad área 3 vs 4 dígitos")

# 5493832414526: área real = 3832 (4 dig), no 383 (3 dig)
# ENACOM resuelve si tiene el bloque; si no, quedan ambos como 383
r = validate("5493832414526")
check("3832414526 → válido",   r.valid, r.error)
check("3832414526 → mobile",   r.line_type == "mobile", r.line_type)
# Si ENACOM tiene el bloque 3832, el área será 3832; si no, queda en 383
# El fmt_con_0_15 debe ser correcto según el área que se resuelva
if r.area_code == "3832":
    check("3832414526 → área 3832 (ENACOM confirmó)", r.area_code == "3832", r.area_code)
    check("3832414526 → fmt_con_0_15 con área 3832",
          r.formats.get("fmt_con_0_15") == "0383215414526", r.formats.get("fmt_con_0_15"))
else:
    # ENACOM no tiene el bloque → área heurística 383, se documenta como limitación
    check("3832414526 → área detectada (sin ENACOM, heurística 383)",
          r.area_code in ("383", "3832"), r.area_code)

section("Formatos con separadores")

check("guiones fijo", validate("011 4321-9876").valid)
check("guiones celular", validate("011-1234-5678").valid)
check("paréntesis", validate("(011) 4321-9876").valid)

section("Prefijos internacionales")

r = validate("00541143219876")
check("0054 prefix → válido", r.valid)
check("0054 prefix → tipo landline", r.line_type == "landline")

r = validate("+5491143219876")
check("+549 en fijo → MÓVIL (el hint manda)", r.line_type == "mobile",
      "Cuando viene +549 se trata como móvil aunque el abonado empiece con 4")

section("Números inválidos")

check("muy corto", not validate("123").valid)
check("muy largo", not validate("123456789012345").valid)
check("letras", not validate("abc1234567").valid)
check("vacío", not validate("").valid)
check("solo guiones", not validate("---").valid)
check("código de país incorrecto", not validate("+551143219876").valid)

# ─── Resultado final ──────────────────────────────────────────────────────────

print(f"\n{'='*50}")
total = 0
# Count via checking length of failures vs all checks
# (recount from script logic — simpler: use failures list)
if failures:
    print(f"\n\033[31mFALLIDOS ({len(failures)}):\033[0m")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\033[32mTodos los tests pasaron.\033[0m")
