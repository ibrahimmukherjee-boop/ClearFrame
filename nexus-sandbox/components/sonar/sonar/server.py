from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from sonar.engine import SonarEngine


class ScanBody(BaseModel):
    agent: str = "demo-agent"
    prompt: str
    response: str = ""
    model: str = "gpt-4o"


def create_app(state_path: Path) -> FastAPI:
    engine = SonarEngine(state_path)
    app = FastAPI(title="Nexus Sonar SOC", version="0.1.0")
    app.state.engine = engine

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "sonar"}

    @app.post("/scan")
    def scan(body: ScanBody) -> dict:
        return engine.scan(agent=body.agent, prompt=body.prompt, response=body.response, model=body.model)

    @app.get("/events")
    def events(limit: int = 50) -> list[dict]:
        return engine.recent_events(limit=limit)

    return app
