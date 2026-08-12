"""AES-256-GCM encrypted credential vault."""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.config import DEFAULT_VAULT_PASSPHRASE, VAULT_PATH, VAULT_SALT_PATH
from app.database import get_conn


def _derive_key(passphrase: str) -> bytes:
    salt = VAULT_SALT_PATH.read_bytes() if VAULT_SALT_PATH.exists() else b"erasys-clearframe-salt-v1"
    if not VAULT_SALT_PATH.exists():
        VAULT_SALT_PATH.write_bytes(salt)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return kdf.derive(passphrase.encode())


def _load_store() -> dict[str, Any]:
    if not VAULT_PATH.exists():
        return {}
    data = json.loads(VAULT_PATH.read_text())
    key = _derive_key(DEFAULT_VAULT_PASSPHRASE)
    aes = AESGCM(key)
    plaintext = aes.decrypt(base64.b64decode(data["nonce"]), base64.b64decode(data["ciphertext"]), None)
    return json.loads(plaintext.decode())


def _save_store(store: dict[str, Any]) -> None:
    key = _derive_key(DEFAULT_VAULT_PASSPHRASE)
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, json.dumps(store).encode(), None)
    VAULT_PATH.write_text(json.dumps({
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }))


def list_keys(unlocked: bool) -> list[dict[str, str]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key_name, updated_at FROM vault_secrets ORDER BY key_name").fetchall()
    return [{"key": r["key_name"], "masked": "sk-•••••••••••••••" if unlocked else "•••••••••••••••••••"} for r in rows]


def set_secret(key_name: str, value: str) -> None:
    store = _load_store()
    store[key_name] = value
    _save_store(store)
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO vault_secrets (key_name, ciphertext, nonce, updated_at) VALUES (?, ?, ?, ?)",
            (key_name, "stored", "stored", time.time()),
        )
    if not list_keys(True):
        for default_key in ["OPENAI_API_KEY", "DATABASE_URL", "AWS_ACCESS_KEY"]:
            if default_key not in store:
                store[default_key] = f"placeholder-{default_key.lower()}"
        _save_store(store)
        with get_conn() as conn:
            for k in store:
                conn.execute(
                    "INSERT OR IGNORE INTO vault_secrets (key_name, ciphertext, nonce, updated_at) VALUES (?, ?, ?, ?)",
                    (k, "stored", "stored", time.time()),
                )


def get_secret(key_name: str) -> str | None:
    store = _load_store()
    return store.get(key_name)


def ensure_defaults() -> None:
    store = _load_store()
    changed = False
    for key in ["OPENAI_API_KEY", "DATABASE_URL", "AWS_ACCESS_KEY", "GITHUB_TOKEN", "SLACK_BOT_TOKEN"]:
        if key not in store:
            store[key] = f"local-{key.lower()}-dev"
            changed = True
    if changed:
        _save_store(store)
        with get_conn() as conn:
            for k in store:
                conn.execute(
                    "INSERT OR IGNORE INTO vault_secrets (key_name, ciphertext, nonce, updated_at) VALUES (?, ?, ?, ?)",
                    (k, "stored", "stored", time.time()),
                )
