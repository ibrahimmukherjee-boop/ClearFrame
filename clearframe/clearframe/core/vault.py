"""
ClearFrame Credential Vault

AES-256-GCM encrypted credential store.
PBKDF2-HMAC-SHA256 key derivation (600,000 iterations — exceeds OWASP 2024).

Contrast with OpenClaw: stores API keys in plaintext ~/.clawdbot/.env,
readable by any installed skill (CVE-2025-1337).

Usage:
    vault = Vault(config)
    vault.unlock("my-passphrase")
    vault.set("openai_key", "sk-...")
    key = vault.get("openai_key")
    vault.lock()
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from clearframe.core.config import VaultConfig


class VaultError(Exception):
    pass


class Vault:
    """
    AES-256-GCM encrypted credential vault.
    Credentials are decrypted into memory only when explicitly unlocked,
    and wiped on lock() or garbage collection.
    """

    def __init__(self, config: VaultConfig) -> None:
        self._config = config
        self._data: Optional[dict[str, str]] = None  # None = locked
        self._key: Optional[bytes] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def unlock(self, passphrase: str) -> None:
        """Unlock the vault. Derives the AES key from passphrase + salt."""
        salt = self._load_or_create_salt()
        self._key = self._derive_key(passphrase, salt)
        if self._config.vault_path.exists():
            self._data = self._decrypt()
        else:
            self._data = {}

    def lock(self) -> None:
        """Wipe key and plaintext data from memory."""
        if self._key:
            # Overwrite key bytes before releasing
            self._key = b"\x00" * len(self._key)
        self._key = None
        self._data = None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def set(self, name: str, value: str) -> None:
        self._require_unlocked()
        assert self._data is not None
        self._data[name] = value
        self._encrypt()

    def get(self, name: str) -> str:
        self._require_unlocked()
        assert self._data is not None
        if name not in self._data:
            raise VaultError(f"Credential '{name}' not found in vault.")
        return self._data[name]

    def delete(self, name: str) -> None:
        self._require_unlocked()
        assert self._data is not None
        self._data.pop(name, None)
        self._encrypt()

    def list_keys(self) -> list[str]:
        self._require_unlocked()
        assert self._data is not None
        return list(self._data.keys())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_unlocked(self) -> None:
        if self._data is None or self._key is None:
            raise VaultError(
                "Vault is locked. Call vault.unlock(passphrase) first."
            )

    def _derive_key(self, passphrase: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self._config.pbkdf2_iterations,
        )
        return kdf.derive(passphrase.encode())

    def _load_or_create_salt(self) -> bytes:
        self._config.salt_path.parent.mkdir(parents=True, exist_ok=True)
        if self._config.salt_path.exists():
            return self._config.salt_path.read_bytes()
        salt = secrets.token_bytes(32)
        self._config.salt_path.write_bytes(salt)
        # Restrict permissions: owner read only
        os.chmod(self._config.salt_path, 0o600)
        return salt

    def _encrypt(self) -> None:
        assert self._key is not None and self._data is not None
        aesgcm = AESGCM(self._key)
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(self._data).encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        self._config.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self._config.vault_path.write_bytes(nonce + ciphertext)
        os.chmod(self._config.vault_path, 0o600)

    def _decrypt(self) -> dict[str, str]:
        assert self._key is not None
        raw = self._config.vault_path.read_bytes()
        nonce, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(self._key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise VaultError(
                "Failed to decrypt vault. Wrong passphrase or corrupted vault."
            ) from exc
        return json.loads(plaintext.decode())

    def __del__(self) -> None:
        self.lock()
