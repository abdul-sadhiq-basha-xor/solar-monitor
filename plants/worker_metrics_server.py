"""
Expose /metrics for the Celery worker so Prometheus can scrape without timing out.

Two modes:

1. **Subprocess mode (default)**  
   A small helper process listens on WORKER_METRICS_PORT and serves the contents
   of a metrics file. The worker (parent) writes that file every second. The
   scraper talks only to the helper process, so it is never blocked by the
   worker's GIL or long tasks. The helper is started and stopped with the worker.

2. **In-process mode**  
   If the helper process cannot be started (e.g. port in use), we fall back to
   an in-process HTTP server with a cached response (same process as the worker).
"""

import atexit
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from prometheus_client.exposition import generate_latest

from .metrics import WORKER_REGISTRY

WORKER_METRICS_PORT = 9100

# Subprocess mode: process and file path for cleanup
_metrics_process: Optional[subprocess.Popen] = None
_metrics_file_path: Optional[str] = None
_file_refresh_stop = threading.Event()


def _project_root() -> str:
    """Project root (parent of package containing this file)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_file_server_subprocess() -> None:
    """
    Entry point for the metrics helper subprocess.
    Reads CELERY_METRICS_FILE and CELERY_METRICS_PORT from env and serves the
    file at GET /metrics until the process is killed.
    """
    path = os.environ.get("CELERY_METRICS_FILE", "")
    port = int(os.environ.get("CELERY_METRICS_PORT", str(WORKER_METRICS_PORT)))
    if not path:
        sys.exit(1)

    class _FileHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            try:
                with open(path, "rb") as f:
                    output = f.read()
            except FileNotFoundError:
                output = b""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)

        def log_message(self, format, *args):  # noqa: A002
            pass

    server = HTTPServer(("0.0.0.0", port), _FileHandler)
    server.serve_forever()


def _file_refresh_loop(metrics_path: str) -> None:
    """In worker process: write metrics to file every second."""
    while not _file_refresh_stop.wait(1.0):
        try:
            output = generate_latest(WORKER_REGISTRY)
            with open(metrics_path, "wb") as f:
                f.write(output)
        except Exception:
            pass


def _kill_metrics_process() -> None:
    global _metrics_process, _metrics_file_path, _file_refresh_stop
    _file_refresh_stop.set()
    if _metrics_process is not None and _metrics_process.poll() is None:
        _metrics_process.terminate()
        try:
            _metrics_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _metrics_process.kill()
    _metrics_process = None
    if _metrics_file_path and os.path.isfile(_metrics_file_path):
        try:
            os.unlink(_metrics_file_path)
        except OSError:
            pass
    _metrics_file_path = None


def start_metrics_server(port: int = WORKER_METRICS_PORT) -> Optional[HTTPServer]:
    """
    Start metrics export for the worker. Prefers a separate subprocess that
    serves a metrics file so scrapes never block on the worker. Falls back to
    an in-process server with cached output if the subprocess cannot bind.
    """
    global _metrics_process, _metrics_file_path, _file_refresh_stop

    global _metrics_file_path
    fd, _metrics_file_path = tempfile.mkstemp(suffix=".prometheus", prefix="celery_metrics_")
    os.close(fd)
    atexit.register(_kill_metrics_process)

    try:
        output = generate_latest(WORKER_REGISTRY)
        with open(_metrics_file_path, "wb") as f:
            f.write(output)
    except Exception:
        pass

    env = os.environ.copy()
    env["CELERY_METRICS_FILE"] = _metrics_file_path
    env["CELERY_METRICS_PORT"] = str(port)
    cwd = _project_root()

    try:
        _metrics_process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from plants.worker_metrics_server import _run_file_server_subprocess; _run_file_server_subprocess()",
            ],
            env=env,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        _metrics_process = None
        _run_inprocess_server(port)
        return None

    # Give the subprocess a moment to bind
    time.sleep(0.2)
    if _metrics_process.poll() is not None:
        _metrics_process = None
        _run_inprocess_server(port)
        return None

    _file_refresh_stop = threading.Event()
    threading.Thread(target=_file_refresh_loop, args=(_metrics_file_path,), daemon=True).start()
    atexit.register(_kill_metrics_process)
    print(f"[Prometheus] Worker metrics available → http://localhost:{port}/metrics (helper process)")
    return None


# ---------- In-process fallback (cached) ----------
_cached_output: bytes = b""
_cache_lock = threading.Lock()


def _refresh_cache() -> None:
    global _cached_output
    try:
        out = generate_latest(WORKER_REGISTRY)
        with _cache_lock:
            _cached_output = out
    except Exception:
        pass


def _run_inprocess_server(port: int) -> None:
    """Fallback: run HTTP server and cache refresher in worker process."""
    class _CachedHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            try:
                with _cache_lock:
                    out = _cached_output
                if not out:
                    _refresh_cache()
                    with _cache_lock:
                        out = _cached_output
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                return

        def log_message(self, format, *args):  # noqa: A002
            pass

    _refresh_cache()
    try:
        server = HTTPServer(("0.0.0.0", port), _CachedHandler)
    except OSError as exc:
        print(f"[Prometheus] FAILED to start metrics on port {port}: {exc}. Metrics disabled.")
        return

    def serve():
        server.serve_forever()

    def refresh_loop():
        while True:
            time.sleep(1.0)
            _refresh_cache()

    threading.Thread(target=serve, daemon=True).start()
    threading.Thread(target=refresh_loop, daemon=True).start()
    print(f"[Prometheus] Worker metrics available → http://localhost:{port}/metrics (in-process)")
