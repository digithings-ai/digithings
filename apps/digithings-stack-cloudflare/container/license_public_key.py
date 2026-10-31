"""Print the public half of this stack's digikey signing key, for license checks.

digichat sends its license JWT to digigraph as ``X-Digi-License``. digigraph
checks it against ``DIGIKEY_PUBLIC_KEY_PEM`` before it allows a hosted
capability (web search, header-driven corpus selection). The license is
signed with the same RS256 key digikey uses here, so the public key can be
derived from ``DIGIKEY_PRIVATE_KEY_PEM`` instead of being kept as a second
secret that has to change on every key rotation.

Prints an SPKI PEM on stdout, or nothing when the private key is missing or
unreadable. Always exits 0: the entrypoint runs under ``set -eu`` and a
missing key must leave the boot path unchanged (license checks then deny, as
before). Only public key material is ever printed.
"""

from __future__ import annotations

import os
import sys


def public_key_pem(private_pem: str) -> str:
    """SPKI PEM for *private_pem*, or "" when it cannot be loaded."""
    if not private_pem.strip():
        return ""
    try:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
            load_pem_private_key,
        )

        key = load_pem_private_key(private_pem.encode(), password=None)
        return (
            key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        )
    except Exception:  # any failure means "no key"; never block boot
        return ""


def main() -> int:
    pem = public_key_pem(os.environ.get("DIGIKEY_PRIVATE_KEY_PEM", ""))
    if pem:
        sys.stdout.write(pem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
