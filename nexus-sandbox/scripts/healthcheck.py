#!/usr/bin/env python3
"""Health check for all Nexus Protocol sandbox services."""

from __future__ import annotations

import sys

import httpx

SERVICES = {
    "TrustRegistry": "http://127.0.0.1:8001/health",
    "Sonar": "http://127.0.0.1:8002/health",
    "Aegis": "http://127.0.0.1:8003/health",
    "ClearFrame": "http://127.0.0.1:7477/",
    "Dashboard": "http://127.0.0.1:8080/health",
}


def main() -> int:
    ok = True
    print("Nexus Protocol Health Check")
    print("-" * 40)
    with httpx.Client(timeout=5.0) as client:
        for name, url in SERVICES.items():
            try:
                r = client.get(url)
                status = "OK" if r.status_code == 200 else f"HTTP {r.status_code}"
                if r.status_code != 200:
                    ok = False
            except Exception as exc:
                status = f"FAIL ({exc})"
                ok = False
            print(f"  {name:16} {status}")
    print("-" * 40)
    if ok:
        print("All services healthy.")
        return 0
    print("Some services are down.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
