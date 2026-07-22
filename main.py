"""
CLI: validador de números telefónicos argentinos.

Uso:
  python3 main.py validate 1123456789 01143219876
  python3 main.py file numeros.csv --provider simvoz
  python3 main.py file numeros.csv --provider simvoz --output salida.csv
  python3 main.py providers
"""

import argparse
import csv
import sys
import os

from validator import validate, validate_bulk, PhoneResult, _HAS_PHONENUMBERS
from providers import PROVIDERS, format_for_provider, get_provider, OutputTemplate

# Ancho de columnas para la tabla
_COL_WIDTHS = {
    "valido": 5,
    "original": 20,
    "tipo": 8,
    "area": 6,
    "provincia": 22,
    "ciudad": 20,
    "fmt_e164": 18,
    "fmt_con_0": 14,
    "fmt_10dig": 12,
    "proveedor": 18,
}

RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
BOLD   = "\033[1m"


def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{RESET}"


def _valid_str(v: bool) -> str:
    return _color("SI", GREEN) if v else _color("NO", RED)


def _type_str(t: str | None) -> str:
    if t == "mobile":
        return _color("movil", CYAN)
    if t == "landline":
        return _color("fijo", YELLOW)
    return _color(t or "?", DIM)


def _hr(widths: list[int]) -> str:
    return "+" + "+".join("-" * (w + 2) for w in widths) + "+"


def _row(cells: list[str], widths: list[int]) -> str:
    parts = []
    for cell, w in zip(cells, widths):
        # Strip ANSI for length calculation
        clean = _strip_ansi(cell)
        padding = w - len(clean)
        parts.append(f" {cell}{' ' * max(0, padding)} ")
    return "|" + "|".join(parts) + "|"


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def _source_str(src: str) -> str:
    if src == "enacom_db":
        return _color("ENACOM", GREEN)
    if src == "hint":
        return _color("fmt", CYAN)
    return _color("heur.", DIM)


def _repair_badge(r: "PhoneResult") -> str:
    if r.repaired:
        return _color("~", YELLOW)
    return " "


_ALL_FORMAT_KEYS = [
    ("fmt_10dig",      "10dig"),
    ("fmt_con_0",      "con_0"),
    ("fmt_con_0_15",   "0+15"),
    ("fmt_con_9",      "con_9"),
    ("fmt_e164",       "E.164"),
    ("fmt_e164_movil", "E.164_mov"),
    ("fmt_intl",       "intl"),
    ("fmt_asterisk",   "asterisk"),
]


def _mod_color(mod: str | None) -> str:
    if mod in ("CPP", "MPP"):
        return _color(mod or "", CYAN)
    if mod == "BASICA":
        return _color(mod or "", YELLOW)
    return _color(mod or "", DIM)


def _print_table(results: list[PhoneResult], provider_key: str | None,
                 all_formats: bool = False):

    base_headers = ["OK", "~", "Original", "Geo.", "Tipo", "Mod.", "Area", "Operador"]
    base_widths  = [  4,   1,        20,     6,     7,      6,      5,        24    ]

    if all_formats:
        fmt_headers = [label for _, label in _ALL_FORMAT_KEYS]
        fmt_widths  = [max(len(label), 14) for label in fmt_headers]
        headers = base_headers + fmt_headers + ["Fuente"]
        widths  = base_widths  + fmt_widths  + [7]
    elif provider_key:
        p = get_provider(provider_key)
        prov_label = p.name if p else provider_key
        headers = base_headers + ["Localidad", prov_label, "Fuente"]
        widths  = base_widths  + [20, 22, 7]
    else:
        headers = base_headers + ["Localidad", "E.164", "Con 0", "0+15 (CPP)", "Fuente"]
        widths  = base_widths  + [20, 18, 13, 16, 7]

    hr = _hr(widths)
    print(hr)
    print(_row([_color(h, BOLD) for h in headers], widths))
    print(hr)

    valid_count = 0
    repaired_count = 0
    for r in results:
        rep = _repair_badge(r)
        if r.repaired:
            repaired_count += 1

        if r.valid:
            valid_count += 1
            tipo     = _type_str(r.line_type)
            mod      = _mod_color(r.modalidad)
            geo      = _color(r.geografia or "", CYAN if r.geografia == "AMBA" else DIM)
            operador = (r.operador or "")[:24]
            localidad = (r.province or "")[:20]
            fuente   = _source_str(r.source)
            base_cells = [_valid_str(True), rep, r.original, geo, tipo, mod,
                          r.area_code or "", operador]

            if all_formats:
                fmt_cells = [r.formats.get(key, "") for key, _ in _ALL_FORMAT_KEYS]
                cells = base_cells + fmt_cells + [fuente]
            elif provider_key:
                fmt = format_for_provider(r.formats, r.line_type, provider_key) or ""
                cells = base_cells + [localidad, fmt, fuente]
            else:
                cpp_fmt = r.formats.get("fmt_con_0_15", "") if r.modalidad in ("CPP","MPP") else ""
                cells = base_cells + [
                    localidad,
                    r.formats.get("fmt_e164", ""),
                    r.formats.get("fmt_con_0", ""),
                    cpp_fmt,
                    fuente,
                ]
        else:
            error = _color(r.error or "?", RED)
            cells = [_valid_str(False), rep, r.original, error] + [""] * (len(headers) - 4)

        print(_row(cells, widths))

    print(hr)
    invalid = len(results) - valid_count
    print(f"\n{_color(str(valid_count), GREEN)} válidos / "
          f"{_color(str(invalid), RED)} inválidos / "
          f"{BOLD}{len(results)}{RESET} total"
          + (f"  ({_color(str(repaired_count), YELLOW)} reparados ~)" if repaired_count else ""))

    repaired = [r for r in results if r.repaired]
    if repaired:
        print()
        for r in repaired:
            n10 = r.formats.get("fmt_10dig", "")
            print(f"  {_color('~', YELLOW)} {r.original!r:22} → {n10}  [{r.repair_note}]")
    if not _HAS_PHONENUMBERS:
        print(_color("  [ENACOM DB activa | pip install phonenumbers para validación extra]", DIM))


def _write_csv(results: list[PhoneResult], path: str):
    if not results:
        return
    rows = [r.to_dict() for r in results]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_provider_csv(results: list[PhoneResult], provider_key: str, path: str,
                        only_valid: bool = False) -> tuple[int, int]:
    """
    Genera un CSV listo para importar en el carrier/discador.
    Devuelve (filas_escritas, invalidos_omitidos).
    """
    from providers import get_provider, format_for_provider

    provider = get_provider(provider_key)
    if not provider:
        raise ValueError(f"Proveedor desconocido: {provider_key!r}")

    tmpl: OutputTemplate = provider.template

    # Construir fieldnames respetando el orden del template
    fieldnames = [tmpl.phone_column]
    fieldnames += [col_name for _, col_name in tmpl.meta_fields]
    fieldnames += list(tmpl.static_fields.keys())

    enc = tmpl.encoding + ("-sig" if tmpl.bom else "")
    written = skipped = 0

    with open(path, "w", newline="", encoding=enc) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=tmpl.delimiter,
                                extrasaction="ignore")
        writer.writeheader()

        for r in results:
            if not r.valid:
                skipped += 1
                if only_valid:
                    continue
                # fila con número original tal como vino, resto vacío
                row = {k: "" for k in fieldnames}
                row[tmpl.phone_column] = r.original
                writer.writerow(row)
                continue

            numero = format_for_provider(r.formats, r.line_type, provider_key) or ""
            row = {tmpl.phone_column: numero}

            # Campos de metadata del resultado
            for attr, col_name in tmpl.meta_fields:
                row[col_name] = getattr(r, attr, "") or ""

            # Campos estáticos (valor default — el usuario los completa)
            for col_name, default_val in tmpl.static_fields.items():
                row[col_name] = default_val

            writer.writerow(row)
            written += 1

    return written, skipped


def _read_file(path: str, column: str | None) -> list[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_excel(path, dtype=str)
            col = int(column) if column and column.isdigit() else (column or df.columns[0])
            if isinstance(col, int):
                return df.iloc[:, col].dropna().str.strip().tolist()
            return df[col].dropna().str.strip().tolist()
        except ImportError:
            print("ERROR: pandas requerido para leer Excel. Instalar con: pip install pandas openpyxl", file=sys.stderr)
            sys.exit(1)
    elif ext == ".csv":
        numbers = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
            col_name = column if column else (fields[0] if fields else None)
            if col_name and col_name.isdigit():
                idx = int(col_name)
                col_name = fields[idx] if idx < len(fields) else None
            for row in reader:
                val = row.get(col_name, "").strip() if col_name else list(row.values())[0].strip()
                if val:
                    numbers.append(val)
        return numbers
    else:
        # TXT: un número por línea
        with open(path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]


def cmd_validate(args):
    results = validate_bulk(args.numbers, default_area=args.default_area)
    _print_table(results, args.provider, all_formats=args.all_formats)


def cmd_file(args):
    numbers = _read_file(args.filepath, args.column)
    if not numbers:
        print("ERROR: no se encontraron números en el archivo.", file=sys.stderr)
        sys.exit(1)

    print(f"Procesando {len(numbers)} números...")
    results = validate_bulk(numbers, default_area=args.default_area)

    if args.output:
        if args.provider:
            written, skipped = _write_provider_csv(
                results, args.provider, args.output, only_valid=args.only_valid
            )
            p = get_provider(args.provider)
            pname = p.name if p else args.provider
            print(f"Guardado en {args.output} para {pname}: {written} válidos, {skipped} inválidos")
        else:
            if args.only_valid:
                results = [r for r in results if r.valid]
            _write_csv(results, args.output)
            print(f"Guardado en {args.output} ({len(results)} registros, formato completo)")
    else:
        if args.only_valid:
            results = [r for r in results if r.valid]
        _print_table(results, args.provider, all_formats=args.all_formats)


def cmd_export(args):
    """
    Exporta una lista de números al formato exacto que pide un carrier o discador.
    Atajo de: file ARCHIVO --provider X --only-valid --output SALIDA
    """
    numbers = _read_file(args.filepath, args.column)
    if not numbers:
        print("ERROR: no se encontraron números en el archivo.", file=sys.stderr)
        sys.exit(1)

    provider = get_provider(args.provider)
    if not provider:
        print(f"ERROR: proveedor desconocido: {args.provider!r}", file=sys.stderr)
        print(f"Disponibles: {', '.join(PROVIDERS)}", file=sys.stderr)
        sys.exit(1)

    out = args.output or f"{os.path.splitext(args.filepath)[0]}_{args.provider}.csv"

    print(f"Procesando {len(numbers)} números para {provider.name}...")
    results = validate_bulk(numbers, default_area=args.default_area)

    valid_total   = sum(1 for r in results if r.valid)
    invalid_total = len(results) - valid_total

    written, skipped = _write_provider_csv(
        results, args.provider, out, only_valid=args.only_valid
    )

    tmpl = provider.template
    cols = [tmpl.phone_column]
    cols += [c for _, c in tmpl.meta_fields]
    cols += list(tmpl.static_fields.keys())

    print(f"\nProveedor : {provider.name}")
    print(f"  Columnas: {', '.join(cols)}")
    print(f"  Formato  fijo : {provider.landline_format}")
    print(f"  Formato móvil : {provider.mobile_format}")
    if provider.notes:
        print(f"  Nota    : {provider.notes}")
    print(f"\nArchivo   : {out}")
    print(f"  Total   : {len(results)}")
    print(f"  Válidos : {_color(str(valid_total), GREEN)}")
    print(f"  Inválidos: {_color(str(invalid_total), RED)}"
          + (" (incluidos como fila vacía)" if not args.only_valid else " (omitidos)"))
    print(f"  Escritos: {written}")
    if provider.template.static_fields:
        print(f"\n  {_color('NOTA:', YELLOW)} Las columnas {list(provider.template.static_fields.keys())} "
              f"tienen valores vacíos/default — completar antes de importar al discador.")


def cmd_providers(args):
    carriers  = {k: p for k, p in PROVIDERS.items() if k not in ("vicidial", "goautodial", "astervoip")}
    discadors = {k: p for k, p in PROVIDERS.items() if k in ("vicidial", "goautodial", "astervoip")}

    def _section(title, subset):
        print(f"\n{_color(title, BOLD)}")
        print(f"{'Clave':<20} {'Nombre':<25} {'Formato fijo':<22} {'Formato móvil':<22} Notas")
        print("-" * 110)
        for key, p in subset.items():
            tmpl_cols = [p.template.phone_column]
            if p.template.meta_fields:
                tmpl_cols += [c for _, c in p.template.meta_fields]
            if p.template.static_fields:
                tmpl_cols += [f"({len(p.template.static_fields)} extra)"]
            col_hint = f"  → cols: {', '.join(tmpl_cols[:4])}"
            print(f"{key:<20} {p.name:<25} {p.landline_format:<22} {p.mobile_format:<22} {p.notes}")
            if p.template.static_fields:
                print(f"{'':>20}{col_hint}")
        print()

    _section("Carriers SIP / trunks", carriers)
    _section("Discadores (dialers)", discadors)


def cmd_stats(args):
    import numgeo as _ng
    if not _ng.is_loaded():
        print("Base ENACOM no disponible (falta data/numgeo_enacom.csv)")
        return
    s = _ng.stats()
    print(f"\nBase ENACOM cargada:")
    print(f"  Bloques totales : {s['total_bloques']:,}")
    print(f"  Indicativos     : {s['indicativos']}")
    print(f"  Móvil           : {s['movil']:,}")
    print(f"  Fijo            : {s['fijo']:,}")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="validador",
        description="Validador de números telefónicos argentinos para discadores"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── validate ──────────────────────────────────────────────────
    p_val = sub.add_parser("validate", help="Valida números pasados como argumentos")
    p_val.add_argument("numbers", nargs="+", help="Números a validar")
    p_val.add_argument("--provider", "-p", default=None, help="Proveedor destino")
    p_val.add_argument("--all-formats", "-f", action="store_true", help="Mostrar todos los formatos")
    p_val.add_argument("--default-area", "-a", default="11",
                       help="Área a asumir para números incompletos (default: 11 = BA)")
    p_val.set_defaults(func=cmd_validate)

    # ── file ──────────────────────────────────────────────────────
    p_file = sub.add_parser("file", help="Procesa un archivo CSV/TXT/Excel")
    p_file.add_argument("filepath", help="Ruta al archivo")
    p_file.add_argument("--column", "-c", default=None, help="Columna (nombre o índice)")
    p_file.add_argument("--provider", "-p", default=None, help="Proveedor destino")
    p_file.add_argument("--output", "-o", default=None, help="Archivo de salida CSV")
    p_file.add_argument("--only-valid", action="store_true", help="Solo incluir números válidos")
    p_file.add_argument("--all-formats", "-f", action="store_true", help="Mostrar todos los formatos")
    p_file.add_argument("--default-area", "-a", default="11",
                       help="Área a asumir para números incompletos (default: 11 = BA)")
    p_file.set_defaults(func=cmd_file)

    # ── export ────────────────────────────────────────────────────
    p_exp = sub.add_parser(
        "export",
        help="Exporta al formato exacto del carrier o discador (atajo para file + provider + output)"
    )
    p_exp.add_argument("filepath",  help="Archivo de entrada (CSV/TXT/Excel)")
    p_exp.add_argument("provider",  help="Clave del carrier o discador (ver: providers)")
    p_exp.add_argument("--column",       "-c", default=None, help="Columna del número")
    p_exp.add_argument("--output",       "-o", default=None,
                       help="Archivo de salida (default: <entrada>_<provider>.csv)")
    p_exp.add_argument("--only-valid",   action="store_true",
                       help="Omitir inválidos (default: se incluyen como fila vacía)")
    p_exp.add_argument("--default-area", "-a", default="11",
                       help="Área por defecto para números incompletos")
    p_exp.set_defaults(func=cmd_export)

    # ── providers ─────────────────────────────────────────────────
    p_prov = sub.add_parser("providers", help="Lista carriers y discadores disponibles")
    p_prov.set_defaults(func=cmd_providers)

    # ── stats ─────────────────────────────────────────────────────
    p_stats = sub.add_parser("stats", help="Estado de la base ENACOM cargada")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
