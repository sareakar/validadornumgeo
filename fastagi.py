"""
FastAGI server — valida números telefónicos argentinos desde el dialplan de Asterisk.

Protocolo: AGI sobre TCP (FastAGI).
Puerto por defecto: 4573

Uso en dialplan:
  ; Pasar el número como argumento
  AGI(agi://localhost:4573/validate,${NUMERO})

  ; Con provider_key (opcional) para pedir el string listo para Dial():
  AGI(agi://localhost:4573/validate,${NUMERO},${AREA},${PROVIDER_KEY},${PREFIX})

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
  ;
  ; Solo si se pasó provider_key (agi_arg_3):
  ; TELVAL_DIAL        string completo listo para Dial() = prefix + formato
  ;                    del proveedor (ej. "" + "01130032202"). Vacío si el
  ;                    número es inválido o el provider_key no existe.
  ; TELVAL_DIAL_ERROR  "" | "numero_invalido" | "provider_desconocido"

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

  ; Ejemplo con provider_key/prefix por trunk (round robin, un AGI por
  ; trunk candidato — ver providers.py para las claves disponibles y
  ; docs/PRUEBA_AGI_LXC1324.md para el diseño completo):
  exten => _X.,1,Set(TRUNK=${DB(SIP/750/trunk)})
   same => n,AGI(agi://localhost:4573/validate,${EXTEN},11,${DB(SIP/750/provider)},${DB(SIP/750/prefix)})
   same => n,GotoIf($["${TELVAL_DIAL}" = ""]?siguiente_trunk,1)
   same => n,Dial(SIP/750/${TELVAL_DIAL},60)

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
from providers import format_for_provider

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

        # ── Obtener argumentos: número, área, provider_key, prefix ──
        number = headers.get("agi_arg_1", "").strip()
        default_area = headers.get("agi_arg_2", "").strip() or None
        provider_key = headers.get("agi_arg_3", "").strip()
        prefix = headers.get("agi_arg_4", "").strip()

        if not number:
            # Intentar con agi_extension como fallback
            number = headers.get("agi_extension", "").strip()

        logger.info(
            "AGI validate: %r (default_area=%s, provider_key=%r)",
            number, default_area, provider_key,
        )

        # ── Validar ───────────────────────────────────────────────
        r = validate(number, default_area=default_area)

        # ── Enviar variables al canal ─────────────────────────────
        vars_to_set = build_vars(r, provider_key, prefix)
        for name, value in vars_to_set.items():
            self._set_var(name, value)

        # ── Retornar resultado a Asterisk ─────────────────────────
        self._send("VERBOSE \"TELVAL: %s → %s %s [%s]\" 1" % (
            number,
            r.formats.get("fmt_10dig", "?") if r.valid else "INVALID",
            r.modalidad or r.line_type or "",
            r.source,
        ))

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


def build_vars(r, provider_key: str = "", prefix: str = "") -> dict:
    """
    Arma el diccionario de variables TELVAL_* a partir de un PhoneResult.
    Función de módulo (no método) para poder testearla sin levantar un
    socket real.
    """
    if r.valid:
        is_cpp = r.modalidad in ("CPP", "MPP")
        v = {
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
        v = {
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

    # provider_key es opcional — si no vino, comportamiento idéntico al
    # de antes (retrocompatible con dialplans que no lo usan).
    if provider_key:
        v.update(_dial_vars(r, provider_key, prefix))

    return v


def _dial_vars(r, provider_key: str, prefix: str) -> dict:
    """TELVAL_DIAL / TELVAL_DIAL_ERROR — string listo para Dial() por trunk."""
    if not r.valid:
        return {"TELVAL_DIAL": "", "TELVAL_DIAL_ERROR": "numero_invalido"}
    fmt = format_for_provider(r.formats, r.line_type, provider_key)
    if fmt is None:
        return {"TELVAL_DIAL": "", "TELVAL_DIAL_ERROR": "provider_desconocido"}
    return {"TELVAL_DIAL": f"{prefix}{fmt}", "TELVAL_DIAL_ERROR": ""}


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # Default de Python (5) es demasiado chico para ráfagas de discador —
    # con >5 conexiones simultáneas, las que exceden el backlog pierden el
    # primer SYN y el cliente reintenta ~1s después (medido en producción,
    # ver docs/PRUEBA_AGI_LXC1324.md). 128 cubre ráfagas grandes sin costo.
    request_queue_size = 128


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
