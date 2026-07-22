"""
REST API para validación de números telefónicos argentinos.
Sin dependencias externas — usa http.server de la stdlib.

Endpoints:
  GET  /validate?number=1130032202[&provider=simvoz][&default_area=11]
  POST /validate/batch   body: {"numbers": [...], "provider": "simvoz"}
  GET  /providers
  GET  /stats
  GET  /health

Respuesta JSON:
  {
    "valid": true,
    "geografia": "AMBA",
    "tipo": "mobile",
    "modalidad": "CPP",
    "operador": "Telecom",
    "area": "11",
    "formats": {
      "fmt_10dig": "1130032202",
      "fmt_con_0": "01130032202",
      "fmt_con_0_15": "0111530032202",
      "fmt_e164": "+541130032202",
      "fmt_e164_movil": "+5491130032202",
      ...
    },
    "source": "enacom_db",
    "error": null
  }
"""

import json
import sys
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))
from validator import validate, validate_bulk
from providers import PROVIDERS, format_for_provider
import numgeo as _numgeo

logger_name = "api"
import logging
logger = logging.getLogger(logger_name)


def _result_to_json(r, provider: str | None = None) -> dict:
    d = {
        "valid":      r.valid,
        "original":   r.original,
        "geografia":  r.geografia,
        "tipo":       r.line_type,
        "modalidad":  r.modalidad,
        "operador":   r.operador,
        "area":       r.area_code,
        "abonado":    r.subscriber,
        "localidad":  r.province,
        "source":     r.source,
        "repaired":   r.repaired,
        "repair_note": r.repair_note,
        "error":      r.error,
        "formats":    r.formats if r.valid else {},
    }
    if provider and r.valid:
        d["fmt_provider"] = format_for_provider(r.formats, r.line_type, provider)
    return d


class ValidatorHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def _json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, msg: str, status: int = 400):
        self._json({"error": msg}, status)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        def q(key, default=None):
            vals = qs.get(key, [])
            return vals[0] if vals else default

        path = parsed.path.rstrip("/")

        # ── GET /health ───────────────────────────────────────────
        if path == "/health":
            self._json({"status": "ok", "enacom_db": _numgeo.is_loaded()})

        # ── GET /stats ────────────────────────────────────────────
        elif path == "/stats":
            self._json(_numgeo.stats())

        # ── GET /providers ────────────────────────────────────────
        elif path == "/providers":
            data = {
                key: {
                    "name":             p.name,
                    "description":      p.description,
                    "landline_format":  p.landline_format,
                    "mobile_format":    p.mobile_format,
                    "notes":            p.notes,
                }
                for key, p in PROVIDERS.items()
            }
            self._json(data)

        # ── GET / → Web UI ────────────────────────────────────────
        elif path in ("", "/"):
            import web_ui
            web_ui.handle_index(self)

        # ── GET /validate?number=...&provider=...&default_area=... ─
        elif path == "/validate":
            number = q("number") or q("n")
            if not number:
                return self._error("Parámetro 'number' requerido")
            provider     = q("provider")
            default_area = q("default_area", "11")
            r = validate(number, default_area=default_area)
            self._json(_result_to_json(r, provider))

        else:
            self._error("Endpoint no encontrado", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # ── POST /ui/analyze y /ui/process → Web UI ──────────────
        if path == "/ui/analyze":
            import web_ui
            web_ui.handle_analyze(self)

        elif path == "/ui/process":
            import web_ui
            web_ui.handle_process(self)

        # ── POST /validate/batch ──────────────────────────────────
        elif path in ("/validate/batch", "/batch"):
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return self._error("Body vacío")
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError as e:
                return self._error(f"JSON inválido: {e}")

            numbers      = body.get("numbers", [])
            provider     = body.get("provider")
            default_area = body.get("default_area", "11")

            if not isinstance(numbers, list):
                return self._error("'numbers' debe ser una lista")
            if len(numbers) > 10_000:
                return self._error("Máximo 10.000 números por request")

            results = validate_bulk(numbers, default_area=default_area)
            data = {
                "total":   len(results),
                "valid":   sum(1 for r in results if r.valid),
                "invalid": sum(1 for r in results if not r.valid),
                "results": [_result_to_json(r, provider) for r in results],
            }
            self._json(data)

        else:
            self._error("Endpoint no encontrado", 404)


class ThreadedHTTPServer(HTTPServer):
    def process_request(self, request, client_address):
        t = threading.Thread(
            target=self._process_request_thread,
            args=(request, client_address),
            daemon=True,
        )
        t.start()

    def _process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def start(host: str = "0.0.0.0", port: int = 8080, block: bool = True):
    server = ThreadedHTTPServer((host, port), ValidatorHandler)
    logger.info("REST API escuchando en http://%s:%d", host, port)
    logger.info("Endpoints: GET /validate?number=... | POST /validate/batch | GET /providers | GET /stats")
    if block:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("API detenida.")
    else:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="REST API validator server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    start(args.host, args.port)
