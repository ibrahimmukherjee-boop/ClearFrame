from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from aegis.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Aegis HITL service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--state", default=str(Path.home() / ".nexus" / "aegis.json"))
    args = parser.parse_args()
    app = create_app(Path(args.state))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
