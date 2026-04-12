"""Tests for the ClearFrame encrypted vault."""

import pytest
from pathlib import Path
from clearframe.core.vault import Vault, VaultError
from clearframe.core.config import VaultConfig


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Vault:
    cfg = VaultConfig(
        vault_path=tmp_path / "vault.enc",
        salt_path=tmp_path / "vault.salt",
    )
    return Vault(cfg)


def test_vault_set_get(tmp_vault: Vault) -> None:
    tmp_vault.unlock("test-password")
    tmp_vault.set("openai_key", "sk-test-123")
    assert tmp_vault.get("openai_key") == "sk-test-123"
    tmp_vault.lock()


def test_vault_locked_raises(tmp_vault: Vault) -> None:
    with pytest.raises(VaultError):
        tmp_vault.get("anything")


def test_vault_multiple_keys(tmp_vault: Vault) -> None:
    tmp_vault.unlock("password")
    tmp_vault.set("key_a", "value_a")
    tmp_vault.set("key_b", "value_b")
    assert tmp_vault.get("key_a") == "value_a"
    assert tmp_vault.get("key_b") == "value_b"


def test_vault_overwrite_key(tmp_vault: Vault) -> None:
    tmp_vault.unlock("password")
    tmp_vault.set("key", "original")
    tmp_vault.set("key", "updated")
    assert tmp_vault.get("key") == "updated"


def test_vault_missing_key_returns_none(tmp_vault: Vault) -> None:
    tmp_vault.unlock("password")
    assert tmp_vault.get("nonexistent") is None


def test_vault_lock_clears_state(tmp_vault: Vault) -> None:
    tmp_vault.unlock("password")
    tmp_vault.set("k", "v")
    tmp_vault.lock()
    with pytest.raises(VaultError):
        tmp_vault.get("k")
