"""Backward-compatible import path — use Mandate Studio (`mandate.py`)."""
from app.services.mandate import (  # noqa: F401
    author,
    import_cedar,
    import_mandate_dsl,
    import_policy,
    import_rego,
    preview,
)
