"""digiquant credential vault (K3).

AES-256-GCM envelope for secrets that only a runner job may open. `envelope.py` holds the
whole implementation; this package re-exports it so callers write
``from digiquant.vault import seal_credential`` rather than reaching into the module.

The envelope is credential-agnostic by design — broker OAuth tokens and API-key pairs
today (`digiquant.brokers.connections`), BYOK LLM keys later — and it is the *one*
implementation of record. A future Supabase Edge Function that accepts user-entered
credentials must reproduce it byte-for-byte against ``tests/dq/vault/vectors.json``.
"""

from digiquant.vault.envelope import (
    DEFAULT_KEY_ID,
    FINGERPRINT_HEX_CHARS,
    GCM_TAG_BYTES,
    KEY_ID_ENV,
    MASTER_KEY_BYTES,
    MASTER_KEY_ENV,
    MAX_PLAINTEXT_BYTES,
    NONCE_BYTES,
    ApiKeyCredential,
    BrokerCredential,
    CredentialLease,
    CredentialLeaseExpiredError,
    EnvelopeAuthenticationError,
    MasterKey,
    OAuthCredential,
    SealedEnvelope,
    VaultConfigurationError,
    VaultError,
    VaultKeyMismatchError,
    VaultPayloadError,
    build_aad,
    canonical_json,
    fingerprint,
    load_master_key,
    open_bytes,
    parse_credential,
    seal_bytes,
    seal_credential,
    unseal_credential,
)

__all__ = [
    "DEFAULT_KEY_ID",
    "FINGERPRINT_HEX_CHARS",
    "GCM_TAG_BYTES",
    "KEY_ID_ENV",
    "MASTER_KEY_BYTES",
    "MASTER_KEY_ENV",
    "MAX_PLAINTEXT_BYTES",
    "NONCE_BYTES",
    "ApiKeyCredential",
    "BrokerCredential",
    "CredentialLease",
    "CredentialLeaseExpiredError",
    "EnvelopeAuthenticationError",
    "MasterKey",
    "OAuthCredential",
    "SealedEnvelope",
    "VaultConfigurationError",
    "VaultError",
    "VaultKeyMismatchError",
    "VaultPayloadError",
    "build_aad",
    "canonical_json",
    "fingerprint",
    "load_master_key",
    "open_bytes",
    "parse_credential",
    "seal_bytes",
    "seal_credential",
    "unseal_credential",
]
