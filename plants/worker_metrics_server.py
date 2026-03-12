"""
Lightweight HTTP server that exposes /metrics for the Celery worker process.

Windows + pool=solo compatible:
  - Uses threading.Thread (no fork / multiprocessing).
  - Daemon thread so it dies cleanly when the worker exits.
  - Port 9090 (change WORKER_METRICS_PORT if needed).
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from prometheus_client import REGISTRY
from prometheus_client.exposition import generate_latest

# Use a dedicated port for the Celery worker metrics HTTP server.
# Make sure this does NOT clash with your main Prometheus server port.
WORKER_METRICS_PORT = 9100


class _MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            output = generate_latest(REGISTRY)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()
            self.wfile.write(output)
        else:
            self.send_response(404)
            self.end_headers()

    # Silence the default access-log noise in worker output
    def log_message(self, format, *args):  # noqa: A002
        pass


def start_metrics_server(port: int = WORKER_METRICS_PORT) -> Optional[HTTPServer]:
    """
    Start the metrics HTTP server in a background daemon thread.
    Returns the HTTPServer instance (mostly for testing).

    If the port is already in use or another OS error occurs, the worker
    will log a clear message but continue running (metrics just disabled).
    """
    try:
        server = HTTPServer(('0.0.0.0', port), _MetricsHandler)
    except OSError as exc:
        print(
            f"[Prometheus] FAILED to start worker metrics server on port {port}: {exc}. "
            f"Worker will continue without Prometheus metrics on this port."
        )
        return None

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[Prometheus] Worker metrics available → http://localhost:{port}/metrics")
    return server