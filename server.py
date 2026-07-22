"""
Servicio combinado: FastAGI (4573) + REST API (8080).

Uso:
  python3 server.py                        # ambos servicios
  python3 server.py --only-agi             # solo FastAGI
  python3 server.py --only-api             # solo REST API
  python3 server.py --agi-port 4573 --api-port 8080
  python3 server.py --agi-host 0.0.0.0    # accesible desde la red (externo)
"""

import argparse
import logging
import signal
import sys
import time

import fastagi
import api


def main():
    p = argparse.ArgumentParser(description="Validador telefónico AR — servidor")
    p.add_argument("--agi-host",  default="127.0.0.1",
                   help="Host FastAGI (127.0.0.1=local, 0.0.0.0=externo)")
    p.add_argument("--agi-port",  type=int, default=4573)
    p.add_argument("--api-host",  default="0.0.0.0")
    p.add_argument("--api-port",  type=int, default=8080)
    p.add_argument("--only-agi",  action="store_true")
    p.add_argument("--only-api",  action="store_true")
    p.add_argument("--debug",     action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)-10s %(levelname)s %(message)s",
    )
    log = logging.getLogger("server")

    servers = []

    if not args.only_api:
        srv = fastagi.start(args.agi_host, args.agi_port, block=False)
        servers.append(srv)
        log.info("FastAGI listo en %s:%d", args.agi_host, args.agi_port)
        log.info("  Dialplan: AGI(agi://%s:%d/validate,${NUMERO})", args.agi_host, args.agi_port)

    if not args.only_agi:
        srv = api.start(args.api_host, args.api_port, block=False)
        servers.append(srv)
        log.info("REST API lista en http://%s:%d", args.api_host, args.api_port)
        log.info("  GET  http://%s:%d/validate?number=1130032202", args.api_host, args.api_port)
        log.info("  POST http://%s:%d/validate/batch", args.api_host, args.api_port)

    if not servers:
        log.error("No se inició ningún servicio.")
        sys.exit(1)

    def _shutdown(sig, frame):
        log.info("Deteniendo servicios...")
        for s in servers:
            if s:
                s.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Servicios activos. Ctrl+C para detener.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
