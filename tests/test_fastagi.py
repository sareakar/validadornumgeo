"""Tests de build_vars() (fastagi.py) — mapeo PhoneResult → variables TELVAL_*."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validator import validate
from fastagi import build_vars

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


# ─── Sin provider_key — retrocompatibilidad ───────────────────────────────────

section("Sin provider_key (retrocompatible con dialplans existentes)")

r = validate("1123456789")  # móvil BA
v = build_vars(r)
check("TELVAL_VALID = 1", v["TELVAL_VALID"] == "1")
check("TELVAL_CON015 presente (CPP)", v["TELVAL_CON015"] == r.formats["fmt_con_0_15"])
check("sin TELVAL_DIAL", "TELVAL_DIAL" not in v)
check("sin TELVAL_DIAL_ERROR", "TELVAL_DIAL_ERROR" not in v)

r_inv = validate("123")  # inválido
v_inv = build_vars(r_inv)
check("inválido → TELVAL_VALID = 0", v_inv["TELVAL_VALID"] == "0")
check("inválido sin provider_key → sin TELVAL_DIAL", "TELVAL_DIAL" not in v_inv)

# ─── Con provider_key — móvil ──────────────────────────────────────────────────

section("Con provider_key — móvil (movistar: E.164 con 9)")

r = validate("1123456789")  # móvil BA, CPP
v = build_vars(r, provider_key="movistar")
check("TELVAL_DIAL = fmt_e164_movil", v["TELVAL_DIAL"] == r.formats["fmt_e164_movil"],
      f"got: {v.get('TELVAL_DIAL')}")
check("TELVAL_DIAL_ERROR vacío", v["TELVAL_DIAL_ERROR"] == "")
check("TELVAL_MODALIDAD = CPP", v["TELVAL_MODALIDAD"] == "CPP", f"got: {v.get('TELVAL_MODALIDAD')}")

section("Con provider_key — modo slim (solo 3 variables, no 16)")

check("exactamente 3 keys", set(v.keys()) == {"TELVAL_DIAL", "TELVAL_DIAL_ERROR", "TELVAL_MODALIDAD"},
      f"got: {sorted(v.keys())}")
check("sin TELVAL_VALID (no se manda en modo slim)", "TELVAL_VALID" not in v)
check("sin TELVAL_10DIG (no se manda en modo slim)", "TELVAL_10DIG" not in v)

# ─── Con provider_key — fijo ───────────────────────────────────────────────────

section("Con provider_key — fijo (personal: con 0)")

r = validate("1143219876")  # fijo BA
v = build_vars(r, provider_key="personal")
check("TELVAL_DIAL = fmt_con_0", v["TELVAL_DIAL"] == r.formats["fmt_con_0"],
      f"got: {v.get('TELVAL_DIAL')}")
check("TELVAL_DIAL_ERROR vacío", v["TELVAL_DIAL_ERROR"] == "")

# ─── provider con landline_format_amba (dainus) ────────────────────────────────

section("provider con landline_format_amba — dainus (AMBA vs interior)")

# Fijo AMBA: dainus rechaza 0+11+abonado (SIP 404 confirmado en
# medimas.centraltelefonica.com.ar), solo acepta el abonado local sin
# área -- landline_format_amba lo cubre.
r = validate("1163296500")  # fijo BA
v = build_vars(r, provider_key="dainus")
check("fijo AMBA (dainus) → abonado sin área", v["TELVAL_DIAL"] == "63296500",
      f"got: {v.get('TELVAL_DIAL')}")

# Fijo interior: dainus sí acepta 0+área+abonado normal (fmt_con_0).
r = validate("02234105000")  # fijo Mar del Plata (BASICA real)
v = build_vars(r, provider_key="dainus")
check("fijo interior (dainus) → fmt_con_0", v["TELVAL_DIAL"] == "02234105000",
      f"got: {v.get('TELVAL_DIAL')}")

# Móvil AMBA e interior: sin override, igual que metrotel/nexo (fmt_con_0_15).
r = validate("1565512215")
v = build_vars(r, provider_key="dainus")
check("móvil AMBA (dainus) → fmt_con_0_15", v["TELVAL_DIAL"] == "0111565512215",
      f"got: {v.get('TELVAL_DIAL')}")

# Un provider SIN landline_format_amba (metrotel) no debe verse afectado
# por este cambio -- mismo fijo AMBA de arriba, resultado distinto.
r = validate("1163296500")
v = build_vars(r, provider_key="metrotel")
check("fijo AMBA (metrotel, retrocompatible) → fmt_con_0 normal",
      v["TELVAL_DIAL"] == "01163296500", f"got: {v.get('TELVAL_DIAL')}")

# ─── Con prefix — se antepone literal al formato del proveedor ───────────────

section("Con prefix (código de acceso del trunk)")

r = validate("1143219876")  # fijo BA
v = build_vars(r, provider_key="personal", prefix="9")
check("TELVAL_DIAL = prefix + fmt_con_0", v["TELVAL_DIAL"] == "9" + r.formats["fmt_con_0"],
      f"got: {v.get('TELVAL_DIAL')}")

# ─── provider_key desconocido ──────────────────────────────────────────────────

section("provider_key desconocido")

r = validate("1123456789")
v = build_vars(r, provider_key="no_existe_este_provider")
check("TELVAL_DIAL vacío", v["TELVAL_DIAL"] == "")
check("TELVAL_DIAL_ERROR = provider_desconocido", v["TELVAL_DIAL_ERROR"] == "provider_desconocido")

# ─── número inválido con provider_key ──────────────────────────────────────────

section("Número inválido con provider_key")

r_inv = validate("123")
v = build_vars(r_inv, provider_key="movistar")
check("TELVAL_DIAL vacío", v["TELVAL_DIAL"] == "")
check("TELVAL_DIAL_ERROR = numero_invalido", v["TELVAL_DIAL_ERROR"] == "numero_invalido")
check("TELVAL_MODALIDAD vacío (inválido)", v["TELVAL_MODALIDAD"] == "")

# ─── Resultado final ────────────────────────────────────────────────────────

print(f"\n{'='*50}")
if failures:
    print(f"\n\033[31mFALLIDOS ({len(failures)}):\033[0m")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\033[32mTodos los tests pasaron.\033[0m")
