"""
ClearFrame — shared exception hierarchy.

Import from here rather than catching generic Exception so callers
can handle ClearFrame errors selectively.
"""


class ClearFrameError(Exception):
    """Base exception for all ClearFrame errors."""


class SessionError(ClearFrameError):
    """Raised for illegal operations within an AgentSession.

    Examples
    --------
    - Calling a tool that is not in permitted_tools
    - Calling a tool after the call limit is reached
    - Attempting to start a session that is already running
    """


class ManifestLockError(ClearFrameError):
    """Raised when a locked GoalManifest is mutated after session start.

    Once AgentSession.start() is called, the GoalManifest is frozen.
    Any attempt to change a field raises this error.

    Example
    -------
    >>> manifest = GoalManifest(goal="test")
    >>> manifest.lock()
    >>> manifest.allow_file_write = True   # raises ManifestLockError
    """


class VaultError(ClearFrameError):
    """Raised for vault access or decryption failures.

    Examples
    --------
    - Wrong passphrase supplied to vault.unlock()
    - Vault file is corrupted (AES-GCM authentication tag mismatch)
    - Accessing a credential before calling vault.unlock()
    """


class AuditError(ClearFrameError):
    """Raised when the audit log HMAC chain is broken.

    Indicates the audit log has been tampered with or corrupted.
    The chain position where the first mismatch occurred is included
    in the error message.
    """


class PluginError(ClearFrameError):
    """Raised for plugin signature verification failures.

    Examples
    --------
    - Ed25519 signature does not verify against the trusted registry key
    - Plugin name not found in the signed registry
    - Plugin payload has been modified after signing
    """
