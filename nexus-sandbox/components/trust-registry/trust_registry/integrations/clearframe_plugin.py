from __future__ import annotations

from trust_registry.models import TrustLevel
from trust_registry.registry import TrustRegistry


class TrustGateError(Exception):
    pass


class TrustGate:
    """ClearFrame integration gate — verifies agent trust before session start."""

    def __init__(self, registry: TrustRegistry, min_trust_level: TrustLevel = TrustLevel.STANDARD) -> None:
        self._registry = registry
        self._min_level = min_trust_level

    def verify(self, certificate_id: str) -> None:
        try:
            if not self._registry.meets_trust_level(certificate_id, self._min_level):
                raise TrustGateError(
                    f"Certificate '{certificate_id}' does not meet minimum trust level "
                    f"{self._min_level.value}."
                )
        except ValueError as exc:
            raise TrustGateError(str(exc)) from exc
