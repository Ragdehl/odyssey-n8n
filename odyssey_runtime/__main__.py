"""Start the configured persistent Odyssey runtime adapter."""

from __future__ import annotations

import os

from .composition import build_runtime_from_environment
from .server import SchemaActivationRestartRequested, serve


def main() -> None:
    """Build the configured production composition and serve the n8n bridge."""
    runtime = build_runtime_from_environment()
    host = os.environ.get("ODYSSEY_RUNTIME_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("ODYSSEY_RUNTIME_PORT", "8765"))
    except ValueError as error:
        raise ValueError("ODYSSEY_RUNTIME_PORT must be an integer") from error
    try:
        serve(runtime, host=host, port=port)
    except SchemaActivationRestartRequested:
        # The DEV unit already uses Restart=on-failure. Avoid spawning a
        # competing runtime in-process or asking the user to restart anything.
        raise SystemExit(75) from None


if __name__ == "__main__":
    main()
