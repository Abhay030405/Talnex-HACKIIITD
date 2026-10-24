"""Start the Python AI worker:  python -m talnex_ai.worker"""
from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from talnex_ai import settings as settings_module
from talnex_ai.db import open_pool
from talnex_ai.worker import handlers as _stages  # noqa: F401  (registers every stage)
from talnex_ai.worker.registry import handlers
from talnex_ai.worker.runner import Worker
from talnex_ai.worker.services import get_services

log = logging.getLogger("talnex.worker")


def health_server(port: int, pool) -> HTTPServer:
    """GET /healthz answers 200 while the database answers, 503 when it doesn't."""

    class Health(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/healthz":
                self.send_response(404)
                self.end_headers()
                return
            try:
                with pool.connection(timeout=3) as conn:
                    conn.execute("SELECT 1")
                code, body = 200, b'{"status":"ok"}'
            except Exception:
                code, body = 503, b'{"status":"database down"}'
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the health checks out of the log
            pass

    server = HTTPServer(("0.0.0.0", port), Health)
    threading.Thread(target=server.serve_forever, name="health", daemon=True).start()
    return server


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        cfg = settings_module.load()
    except settings_module.SettingsError as err:
        log.error("%s", err)
        return 1

    pool = open_pool(cfg.database_url, max_size=cfg.worker.concurrency + 3)
    try:
        get_services(pool)  # build every client now, so a bad setting stops the worker at start, not mid-job
    except Exception as err:
        log.error("could not start the services: %s", err)
        pool.close()
        return 1

    worker = Worker(pool, cfg.database_url, handlers(), worker_id=f"py-{socket.gethostname()}-{os.getpid()}",
                    concurrency=cfg.worker.concurrency, poll_seconds=cfg.worker.poll_seconds,
                    retry_delay_seconds=cfg.worker.retry_delay_seconds)
    health = health_server(cfg.worker.health_port, pool)

    def shutdown(*_):
        log.info("shutting down")
        worker.stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    log.info("python worker started id=%s concurrency=%d stages=%s", worker.worker_id, cfg.worker.concurrency,
             ", ".join(sorted(handlers())))
    worker.run_forever()
    health.shutdown()
    pool.close()
    log.info("python worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
