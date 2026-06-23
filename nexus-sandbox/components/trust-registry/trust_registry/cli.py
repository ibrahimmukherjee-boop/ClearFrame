from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from trust_registry.models import AgentIdentity, CapabilityScope, IssuanceRequest, TrustLevel
from trust_registry.server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="TrustRegistry HTTP service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--state", default=str(Path.home() / ".nexus" / "trust-registry.json"))
    args = parser.parse_args()
    app = create_app(Path(args.state))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
