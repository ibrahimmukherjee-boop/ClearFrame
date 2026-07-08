#!/usr/bin/env python3
"""Health check for unified EC2 gateway."""

from __future__ import annotations

import os
import sys

import httpx

PORT = os.getenv("NEXUS_PORT", "8080")
BASE = f"http://127.0.0.1:{PORT}"


def main() -> int:
    print(f"Nexus EC2 Health Check ({BASE})")
    print("-" * 40)
    ok = True
    with httpx.Client(timeout=5.0) as client:
        try:
            r = client.get(f"{BASE}/health")
            data = r.json()
            print(f"  Gateway          {'OK' if r.status_code == 200 else 'FAIL'}")
            print(f"  Auth required    {data.get('auth_required', '?')}")
            print(f"  Public URL       {data.get('public_url', '?')}")
            for name, info in data.get("services", {}).items():
                status = "OK" if info.get("ok") else "FAIL"
                if not info.get("ok"):
                    ok = False
                print(f"  {name:16} {status}")
        except Exception as exc:
            print(f"  Gateway          FAIL ({exc})")
            ok = False
    print("-" * 40)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
