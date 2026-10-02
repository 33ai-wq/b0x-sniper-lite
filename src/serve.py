"""hood_sniper.serve — Flask server (gunicorn/netcat-free) so the
Worker mirror can dispatch cron-style radar fetches to Python and get
the JSON back.

Routes:
  GET /v1/hood-sniper/radar        — full radar JSON
  GET /v1/hood-sniper/radar/feed   — ranked top events only
  GET /v1/hood-sniper/radar/health — liveness probe

For prod, point CF Worker at gunicorn + this module. For dev, run:
    python -m hood_sniper.serve
    (defaults to localhost:8072)
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import config, engine


# ─── stdlib-only HTTP server (zero deps) ───────────────────────

import http.server
import socketserver


def _radar() -> dict:
    return engine.tick(
        baseline_path=config.RADAR_BASELINE_PATH,
        history_path=config.RADAR_HISTORY_PATH,
    )


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silence stderr access log spam
        return

    def _send_json(self, body: dict, status: int = 200) -> None:
        encoded = json.dumps(body, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 — stdlib naming
        if self.path.startswith("/v1/hood-sniper/radar/feed"):
            payload = _radar()
            events = payload["events"][: config.RADAR_FREE_EVENT_LIMIT]
            payload["events"] = events
            payload["served"] = "feed"
            self._send_json(payload)
        elif self.path.startswith("/v1/hood-sniper/radar/health"):
            self._send_json({
                "status": "ok",
                "service": "hood-sniper",
                "version": "0.1.0",
            })
        elif self.path.startswith("/v1/hood-sniper/radar"):
            self._send_json(_radar())
        else:
            self._send_json({"error": "not_found"}, status=404)


def serve(host: str = "0.0.0.0", port: int | None = None) -> None:  # pragma: no cover
    bind_port = int(port or os.environ.get("HOOD_SNIPER_PORT", "8072"))
    with socketserver.TCPServer((host, bind_port), _Handler) as httpd:
        print(f"[hood-sniper] listening http://{host}:{bind_port}")
        httpd.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    serve()
