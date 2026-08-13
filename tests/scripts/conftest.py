"""Shared fixtures for tests/scripts/."""

from __future__ import annotations

#: Cloudflare credential env vars — shared definition in tests.digi_test_env.
#: Re-export the autouse fixture so it remains active for this suite; rationale
#: for clearing (host-shell wrangler credentials leaking into d1_sync /
#: vectorize_sync tests) is documented there.
from tests.digi_test_env import (  # noqa: F401
    CLOUDFLARE_CREDENTIAL_ENV_VARS as _CLOUDFLARE_CREDENTIAL_ENV_VARS,
)
from tests.digi_test_env import (  # noqa: F401
    clear_cloudflare_credential_env as _clear_cloudflare_credential_env,
)
