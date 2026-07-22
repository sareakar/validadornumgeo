"""
FastAGI server — valida números telefónicos argentinos desde el dialplan de Asterisk.

Protocolo: AGI sobre TCP (FastAGI).
Puerto por defecto: 4573

Uso en dialplan:
  ; Pasar el número como argumento
  AGI(agi://localhost:4573/validate,${NUMERO})

  ; Variables que devuelve:
  ; TELVAL_VALID      1|0
  ; TELVAL_GEO        AMBA|Interior
  ; TELVAL_TIPO       mobile|landline|unknown
  ; TELVAL_MODALIDAD  CPP|MPP|BASICA|
  ; TELVAL_OPERADOR   Movistar|Claro|Personal|Telecom|...
  ; TELVAL_AREA       11|351|261|...
  ; TELVAL_10DIG      1165512215
  ; TELVAL_CON0       01165512215
  ; TELVAL_CON015     0111565512215    (solo CPP/MPP)
  ; TELVAL_E164       +541165512215
  ; TELVAL_E164MOV    +5491165512215   (solo CPP/MPP)
  ; TELVAL_ERROR      formato_invalido|numero_invalido|...
  ; TELVAL_SOURCE     ENACOM|enacom_db|heuristica|hint

Ejemplo de uso completo en dialplan (extensions.conf):
  exten => _X.,1,AGI(agi://localhost:4573/validate,${EXTEN})
   same => n,GotoIf($["${TELVAL_VALID}" != "1"]?invalid,1)
   same => n,GotoIf($["${TELVAL_MODALIDAD}" = "CPP"]?cpp,1)
   same => n,GotoIf($["${TELVAL_MODALIDAD}" = "MPP"]?cpp,1)
   ; Fijo
   same => n,Dial(SIP/${TELVAL_10DIG}@trunk_fijo)
   same => n,Hangup()
  exten => cpp,1,Dial(SIP/${TELVAL_CON015}@trunk_movil)
   same => n,Hangup()
  exten => invalid,1,Playback(invalid-number)
   same => n,Hangup()

Para servidor externo, simplemente cambiar la IP:
  AGI(agi://192.168.1.100:4573/validate,${EXTEN})
"""

import socketserver
import threading
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from validator import validate

logger = logging.getLogger("fastagi")


class AGIHandler(socketserver.StreamRequestHandler):
    """Maneja una conexión FastAGI (un llamado)."""

    def handle(self):
        try:
            self._run()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            logger.exception("Error en AGI handler: %s", e)

    def _run(self):
        # ── Leer headers AGI ─────────────────────────────────────
        headers = {}
        while True:
            line = self.rfile.readline().decode("utf-8", errors="replace").rstrip("\n\r")
            if not line:
                break
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip().lower()] = value.strip()

        # ── Obtener el número desde agi_arg_1 ────────────────────
        number = headers.get("agi_arg_1", "").strip()
        default_area = headers.get("agi_arg_2", "11").strip() or "11"

        if not number:
            # Intentar con agi_extension como fallback
            number = headers.get("agi_extension", "").strip()

        logger.info("AGI validate: %r (default_area=%s)", number, default_area)

        # ── Validar ───────────────────────────────────────────────
        r = validate(number, default_area=default_area)

        # ── Enviar variables al canal ─────────────────────────────
        vars_to_set = self._build_vars(r)
        for name, value in vars_to_set.items():
            self._set_var(name, value)

        # ── Retornar resultado a Asterisk ─────────────────────────
        self._send("VERBOSE \"TELVAL: %s → %s %s [%s]\" 1" % (
            number,
            r.formats.get("fmt_10dig", "?") if r.valid else "INVALID",
            r.modalidad or r.line_type or "",
            r.source,
        ))

    def _build_vars(self, r) -> dict:
        if r.valid:
            is_cpp = r.modalidad in ("CPP", "MPP")
            return {
                "TELVAL_VALID":     "1",
                "TELVAL_GEO":       r.geografia or "",
                "TELVAL_TIPO":      r.line_type or "",
                "TELVAL_MODALIDAD": r.modalidad or "",
                "TELVAL_OPERADOR":  r.operador or "",
                "TELVAL_AREA":      r.area_code or "",
                "TELVAL_10DIG":     r.formats.get("fmt_10dig", ""),
                "TELVAL_CON0":      r.formats.get("fmt_con_0", ""),
                "TELVAL_CON015":    r.formats.get("fmt_con_0_15", "") if is_cpp else "",
                "TELVAL_E164":      r.formats.get("fmt_e164", ""),
                "TELVAL_E164MOV":   r.formats.get("fmt_e164_movil", "") if is_cpp else "",
                "TELVAL_CON9":      r.formats.get("fmt_con_9", "") if is_cpp else "",
                "TELVAL_SOURCE":    r.source,
                "TELVAL_ERROR":     "",
            }
        else:
            return {
                "TELVAL_VALID":     "0",
                "TELVAL_GEO":       "",
                "TELVAL_TIPO":      "",
                "TELVAL_MODALIDAD": "",
                "TELVAL_OPERADOR":  "",
                "TELVAL_AREA":      "",
                "TELVAL_10DIG":     "",
                "TELVAL_CON0":      "",
                "TELVAL_CON015":    "",
                "TELVAL_E164":      "",
                "TELVAL_E164MOV":   "",
                "TELVAL_CON9":      "",
                "TELVAL_SOURCE":    "",
                "TELVAL_ERROR":     r.error or "error_desconocido",
            }

    def _set_var(self, name: str, value: str):
        cmd = f'SET VARIABLE {name} "{value}"\n'
        self.wfile.write(cmd.encode("utf-8"))
        self.wfile.flush()
        # Leer respuesta "200 result=1"
        self.rfile.readline()

    def _send(self, cmd: str):
        self.wfile.write((cmd + "\n").encode("utf-8"))
        self.wfile.flush()
        self.rfile.readline()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start(host: str = "0.0.0.0", port: int = 4573, block: bool = True):
    server = ThreadedTCPServer((host, port), AGIHandler)
    logger.info("FastAGI escuchando en %s:%d", host, port)
    logger.info("Dialplan: AGI(agi://%s:%d/validate,${NUMERO})", host, port)
    if block:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("FastAGI detenido.")
    else:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="FastAGI validator server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=4573)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    start(args.host, args.port)
