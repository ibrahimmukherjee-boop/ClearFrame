# Contributing to ClearFrame

ClearFrame is Apache 2.0 licensed. All contributions are welcome.

## Setup

```bash
git clone https://github.com/ibrahimmukherjee-boop/clearframe
cd clearframe
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v --cov=clearframe
```

## Code style

```bash
ruff check clearframe/ tests/
mypy clearframe/
```

## Submitting a PR

1. Fork the repo
2. Create a branch: `git checkout -b feat/my-feature`
3. Write tests for any new behaviour
4. Run `pytest` and `ruff` — both must pass
5. Open a PR with a clear description of the change

## Reporting security issues

Please **do not** open a public issue for security vulnerabilities.
Email the maintainers directly or use GitHub's private security advisory feature.
