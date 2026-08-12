"""
ClearFrame Plugin Registry
==========================
Only plugins with a valid Ed25519 signature from a trusted registry key
are allowed to be loaded into a ClearFrame session.

Workflow
--------
1.  Plugin author signs the plugin payload (name + version + entrypoint bytes)
    with their private key.
2.  The registry authority countersigns the plugin entry with the
    trusted registry private key.
3.  At load time, PluginRegistry.register() verifies the registry
    countersignature before the plugin callable is accepted.

Usage
-----
    from clearframe.plugins.registry import PluginRegistry

    registry = PluginRegistry(trusted_public_key_pem=REGISTRY_PUB_KEY_PEM)

    # Register a plugin (called during ClearFrame startup / plugin install)
    registry.register(
        name          = "web_search",
        fn            = my_web_search_function,
        signature_b64 = "BASE64_ED25519_SIG_OVER_PAYLOAD",
        payload       = b"web_search:1.0.0:sha256:HASH_OF_ENTRYPOINT",
    )

    # Retrieve a verified plugin callable
    tool_fn = registry.get("web_search")
"""
from __future__ import annotations

import base64
import logging
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from clearframe.core.errors import PluginError

log = logging.getLogger(__name__)


class PluginRegistry:
    """
    Ed25519-verified plugin registry.

    Parameters
    ----------
    trusted_public_key_pem
        PEM-encoded Ed25519 public key of the registry authority.
        Only plugins countersigned by this key will be accepted.
    """

    def __init__(self, trusted_public_key_pem: str) -> None:
        self._pubkey: Ed25519PublicKey = serialization.load_pem_public_key(
            trusted_public_key_pem.encode()
        )  # type: ignore[assignment]
        self._plugins:    dict[str, Callable] = {}
        self._signatures: dict[str, str]      = {}  # name → verified signature

    # ── Public API ────────────────────────────────────────────────────────

    def register(
        self,
        name:          str,
        fn:            Callable,
        signature_b64: str,
        payload:       bytes,
    ) -> None:
        """
        Register a plugin after verifying its Ed25519 signature.

        Parameters
        ----------
        name
            Unique tool name (used as key in GoalManifest.permitted_tools).
        fn
            The callable that implements the plugin.
        signature_b64
            Base64-encoded Ed25519 signature over `payload`.
        payload
            The canonical bytes that were signed — typically
            ``f"{name}:{version}:{sha256_of_entrypoint}".encode()``.

        Raises
        ------
        PluginError
            If the signature is invalid or the payload is malformed.
        """
        try:
            raw_sig = base64.b64decode(signature_b64)
            self._pubkey.verify(raw_sig, payload)
        except InvalidSignature as exc:
            raise PluginError(
                f"Plugin '{name}' rejected — Ed25519 signature verification failed. "
                "The plugin may have been tampered with or signed by an untrusted key."
            ) from exc
        except Exception as exc:
            raise PluginError(
                f"Plugin '{name}' registration error: {exc}"
            ) from exc

        self._plugins[name]    = fn
        self._signatures[name] = signature_b64
        log.info("Plugin '%s' registered with verified signature.", name)

    def get(self, name: str) -> Callable:
        """
        Retrieve a verified plugin callable by name.

        Raises
        ------
        PluginError
            If the plugin has not been registered.
        """
        if name not in self._plugins:
            raise PluginError(
                f"Plugin '{name}' not found in the registry. "
                "Ensure it has been registered with a valid signature before use."
            )
        return self._plugins[name]

    def list_plugins(self) -> list[str]:
        """Return names of all currently registered plugins."""
        return sorted(self._plugins.keys())

    def is_registered(self, name: str) -> bool:
        """Return True if a plugin with this name has been registered."""
        return name in self._plugins

    def get_signature(self, name: str) -> str:
        """Return the base64 signature used to register a plugin."""
        if name not in self._signatures:
            raise PluginError(f"No signature record for plugin '{name}'.")
        return self._signatures[name]

    def unregister(self, name: str) -> None:
        """
        Remove a plugin from the registry (e.g. after a revocation event).
        Silently succeeds if the plugin was not registered.
        """
        self._plugins.pop(name, None)
        self._signatures.pop(name, None)
        log.info("Plugin '%s' unregistered.", name)

    def as_tool_registry(self) -> dict[str, Callable]:
        """
        Return a copy of the verified plugin dict suitable for passing
        directly to AgentSession(tool_registry=...).
        """
        return dict(self._plugins)

    def __len__(self) -> int:
        return len(self._plugins)

    def __repr__(self) -> str:
        return f"PluginRegistry(plugins={self.list_plugins()})"
