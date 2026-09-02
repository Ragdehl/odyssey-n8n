"""Persistent local HTTP adapter for n8n-to-Core requests."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .composition import RuntimeComposition
from .serialization import application_result_to_response

MAX_REQUEST_BYTES = 1_048_576


def serve(runtime: RuntimeComposition, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the bounded runtime contract until the process receives a shutdown signal.

    Args:
        runtime: Long-lived Core composition to invoke.
        host: Explicit bind address; deployment should use the Docker bridge interface for n8n.
        port: Local TCP port for the adapter.

    Raises:
        OSError: If the address cannot be bound or the server cannot run.
    """
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    handler = _handler_for(runtime)
    with ThreadingHTTPServer((host, port), handler) as server:
        server.serve_forever()


def _handler_for(runtime: RuntimeComposition) -> type[BaseHTTPRequestHandler]:
    """Create an HTTP handler closed over one explicit runtime composition."""

    class RuntimeHandler(BaseHTTPRequestHandler):
        """Handle only the health check and JSON execute endpoint."""

        server_version = "OdysseyRuntime/1.0"

        def do_GET(self) -> None:  # noqa: N802
            """Return a bounded readiness response for the health endpoint."""
            if self.path != "/healthz":
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._write_json(HTTPStatus.OK, {"ok": True, "service": "odyssey-runtime"})

        def do_POST(self) -> None:  # noqa: N802
            """Validate one request payload, execute Core, and return public evidence."""
            if self.path != "/execute":
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("request body is too large")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {"request"}:
                    raise ValueError("request payload must contain only request")
                request = payload["request"]
                if not isinstance(request, str) or not request.strip():
                    raise ValueError("request must be a non-empty string")
                result = runtime.execute(request)
                self._write_json(HTTPStatus.OK, application_result_to_response(result))
            except (TypeError, ValueError):
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid request"})
            except Exception:
                self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "runtime failure"})

        def log_message(self, format: str, *args: Any) -> None:
            """Avoid logging request bodies or other potentially sensitive input."""
            del format, args

        def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            """Write one compact JSON response without exposing server internals."""
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return RuntimeHandler
