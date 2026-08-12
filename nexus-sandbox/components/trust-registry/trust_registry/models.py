from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TrustLevel(str, Enum):
    SANDBOX = "SANDBOX"
    RESTRICTED = "RESTRICTED"
    STANDARD = "STANDARD"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


class LicenseTier(str, Enum):
    COMMUNITY = "COMMUNITY"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"


class CapabilityScope(BaseModel):
    can_make_http_requests: bool = False
    can_read_files: bool = False
    can_write_files: bool = False
    can_execute_code: bool = False
    allowed_tools: list[str] = Field(default_factory=list)


class AgentIdentity(BaseModel):
    name: str
    version: str
    owner: str
    public_key_pem: str = ""


class IssuanceRequest(BaseModel):
    agent: AgentIdentity
    requested_trust_level: TrustLevel = TrustLevel.STANDARD
    license_tier: LicenseTier = LicenseTier.COMMUNITY
    capability_scope: CapabilityScope = Field(default_factory=CapabilityScope)
    validity_days: int = 30


class TrustCertificate(BaseModel):
    certificate_id: str
    agent: AgentIdentity
    trust_level: TrustLevel
    license_tier: LicenseTier
    capability_scope: CapabilityScope
    issued_at: float
    expires_at: float
    signature_b64: str
    revoked: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.revoked and time.time() < self.expires_at

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "agent_name": self.agent.name,
            "agent_version": self.agent.version,
            "owner": self.agent.owner,
            "trust_level": self.trust_level.value,
            "license_tier": self.license_tier.value,
            "capabilities": self.capability_scope.model_dump(),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": f"ed25519:{self.signature_b64[:32]}...",
            "status": "revoked" if self.revoked else ("verified" if self.is_valid else "expired"),
        }
