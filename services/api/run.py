#!/usr/bin/env python3
"""Run the Erasys ClearFrame Stack API."""
import os
from pathlib import Path

import uvicorn
from app.config import API_HOST, API_PORT

RELOAD = os.environ.get("CLEARFRAME_RELOAD", "false").lower() in {"1", "true", "yes"}

if __name__ == "__main__":
    kwargs: dict = {"host": API_HOST, "port": API_PORT}
    if RELOAD:
        kwargs.update(reload=True, reload_dirs=[str(Path(__file__).resolve().parent / "app")])
    uvicorn.run("app.main:app", **kwargs)
