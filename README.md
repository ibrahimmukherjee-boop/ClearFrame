# ClearFrame

Open-source agent protocol (`clearframe/`) plus a hosted operator platform:

- **GitHub Pages console:** [`docs/`](docs/) — paper/ink UI with an instant in-browser demo (no backend needed)  
  Live: https://ibrahimmukherjee-boop.github.io/ClearFrame/
- **Backend API:** [`services/api/`](services/api/) — FastAPI, Postgres, Aegis, SafePulse, TrustRegistry, Sonar  
  One-click Render Blueprint: https://dashboard.render.com/blueprint/new?repo=https://github.com/ibrahimmukherjee-boop/ClearFrame

Full setup, environment variables, Docker, and smoke tests: [DEPLOYMENT.md](DEPLOYMENT.md).

The root `clearframe/` Python package is unchanged. Operator APIs live under `services/api/`.
