from __future__ import annotations

import base64
import json
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trust_registry.models import IssuanceRequest, TrustCertificate, TrustLevel


class TrustRegistry:
  """In-memory trust registry with Ed25519-signed agent certificates."""

  _LEVEL_RANK = {
      TrustLevel.SANDBOX: 0,
      TrustLevel.RESTRICTED: 1,
      TrustLevel.STANDARD: 2,
      TrustLevel.ELEVATED: 3,
      TrustLevel.CRITICAL: 4,
  }

  def __init__(self, state_path: Path | None = None) -> None:
      self._state_path = state_path
      self._private_key = Ed25519PrivateKey.generate()
      self._public_pem = self._private_key.public_key().public_bytes(
          encoding=serialization.Encoding.PEM,
          format=serialization.PublicFormat.SubjectPublicKeyInfo,
      ).decode()
      self._certificates: dict[str, TrustCertificate] = {}
      self._crl: set[str] = set()
      if state_path and state_path.exists():
          self._load()

  @property
  def public_key_pem(self) -> str:
      return self._public_pem

  def issue_certificate(self, request: IssuanceRequest) -> TrustCertificate:
      cert_id = f"cert-{uuid.uuid4().hex[:12]}"
      issued_at = time.time()
      expires_at = issued_at + (request.validity_days * 86400)
      payload = json.dumps({
          "certificate_id": cert_id,
          "agent": request.agent.model_dump(),
          "trust_level": request.requested_trust_level.value,
          "issued_at": issued_at,
          "expires_at": expires_at,
      }, sort_keys=True).encode()
      signature = base64.b64encode(self._private_key.sign(payload)).decode()
      cert = TrustCertificate(
          certificate_id=cert_id,
          agent=request.agent,
          trust_level=request.requested_trust_level,
          license_tier=request.license_tier,
          capability_scope=request.capability_scope,
          issued_at=issued_at,
          expires_at=expires_at,
          signature_b64=signature,
      )
      self._certificates[cert_id] = cert
      self._persist()
      return cert

  def verify(self, certificate_id: str) -> TrustCertificate:
      cert = self._certificates.get(certificate_id)
      if cert is None:
          raise ValueError(f"Certificate '{certificate_id}' not found.")
      if certificate_id in self._crl or cert.revoked:
          raise ValueError(f"Certificate '{certificate_id}' is revoked.")
      if time.time() >= cert.expires_at:
          raise ValueError(f"Certificate '{certificate_id}' has expired.")
      return cert

  def revoke(self, certificate_id: str) -> None:
      cert = self._certificates.get(certificate_id)
      if cert is None:
          raise ValueError(f"Certificate '{certificate_id}' not found.")
      cert.revoked = True
      self._crl.add(certificate_id)
      self._persist()

  def list_certificates(self) -> list[TrustCertificate]:
      return list(self._certificates.values())

  def meets_trust_level(self, certificate_id: str, minimum: TrustLevel) -> bool:
      cert = self.verify(certificate_id)
      return self._LEVEL_RANK[cert.trust_level] >= self._LEVEL_RANK[minimum]

  def _persist(self) -> None:
      if not self._state_path:
          return
      self._state_path.parent.mkdir(parents=True, exist_ok=True)
      data = [c.model_dump() for c in self._certificates.values()]
      self._state_path.write_text(json.dumps(data, indent=2))

  def _load(self) -> None:
      data = json.loads(self._state_path.read_text())
      for item in data:
          cert = TrustCertificate.model_validate(item)
          self._certificates[cert.certificate_id] = cert
          if cert.revoked:
              self._crl.add(cert.certificate_id)
