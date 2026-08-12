from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from sonar.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Sonar SOC service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--state", default=str(Path.home() / ".nexus" / "sonar.json"))
    args = parser.parse_args()
    app = create_app(Path(args.state))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
