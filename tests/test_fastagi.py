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

# ─── Con provider_key — fijo ───────────────────────────────────────────────────

section("Con provider_key — fijo (personal: con 0)")

r = validate("1143219876")  # fijo BA
v = build_vars(r, provider_key="personal")
check("TELVAL_DIAL = fmt_con_0", v["TELVAL_DIAL"] == r.formats["fmt_con_0"],
      f"got: {v.get('TELVAL_DIAL')}")
check("TELVAL_DIAL_ERROR vacío", v["TELVAL_DIAL_ERROR"] == "")

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
check("TELVAL_VALID = 0", v["TELVAL_VALID"] == "0")
check("TELVAL_DIAL vacío", v["TELVAL_DIAL"] == "")
check("TELVAL_DIAL_ERROR = numero_invalido", v["TELVAL_DIAL_ERROR"] == "numero_invalido")

# ─── Resultado final ────────────────────────────────────────────────────────

print(f"\n{'='*50}")
if failures:
    print(f"\n\033[31mFALLIDOS ({len(failures)}):\033[0m")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\033[32mTodos los tests pasaron.\033[0m")
