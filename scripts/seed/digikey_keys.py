"""digikey API keys with scopes, for the local stack (plan section 5).

The mint path is digikey's own CLI (`python -m digikey issue-key`), which is
NOT idempotent: every invocation inserts a new row and prints a fresh raw
key. So this seeder does not shell out to it. It reuses digikey's crypto and
DB modules directly and adds the missing idempotency: a key is looked up by
its ``label`` and reused when a non-revoked row already exists.

Raw keys are secrets. They are written to a mode-0600 file and never
printed; this module reports the ``key_prefix`` and the value's length only.

``database_url`` is guarded by :func:`require_local_database` before it is
exported, so a stray ``DIGIKEY_DATABASE_URL`` cannot point the mint at a
production key store.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from scripts.seed.deterministic import DEFAULT_SEED, require_local_database, stable_uuid

#: Scopes the local stack actually exercises. ``digisearch:ingest`` is the
#: one `make seed-digisearch-local` requires; the rest mirror the default
#: session set in digikey/src/digikey/scopes.py DEFAULT_BFF_SESSION_SCOPES.
#: ``(label, scopes)`` pairs. The label is the idempotency key: one
#: non-revoked row per label, reused on every later run.
SEED_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("seed-ingest", ("digisearch:ingest",)),
    ("seed-search", ("digisearch:query",)),
    ("seed-graph", ("digigraph:workflow", "digigraph:chat")),
    ("seed-vault", ("digivault:read",)),
)


@dataclass(frozen=True)
class KeyResult:
    label: str
    key_prefix: str
    tenant_slug: str
    scopes: tuple[str, ...]
    action: str  # "minted" | "reused" | "skipped"
    raw: str | None = None


def ensure_keys(
    *,
    tenant_slug: str,
    database_url: str | None,
    out_path: Path,
    seed: int = DEFAULT_SEED,
    seed_file: bool = True,
) -> list[KeyResult]:
    """Idempotently ensure one digikey key per :data:`SEED_KEYS` entry."""
    if not database_url:
        return [
            KeyResult(
                label=label, key_prefix="", tenant_slug=tenant_slug, scopes=scopes, action="skipped"
            )
            for label, scopes in SEED_KEYS
        ]
    require_local_database(database_url, what="digikey key rows")
    os.environ["DIGIKEY_DATABASE_URL"] = database_url
    from digikey.db import session_factory
    from digikey.db_schema import ApiKeyRow
    from digikey.key_crypto import generate_raw_key, hash_secret

    results: list[KeyResult] = []
    minted: dict[str, str] = {}
    session = session_factory()
    try:
        for label, scopes in SEED_KEYS:
            existing = (
                session.query(ApiKeyRow)
                .filter(ApiKeyRow.label == label, ApiKeyRow.revoked_at.is_(None))
                .one_or_none()
            )
            if existing is not None:
                results.append(
                    KeyResult(
                        label=label,
                        key_prefix=existing.key_prefix,
                        tenant_slug=existing.tenant_slug,
                        scopes=tuple(existing.scopes or ()),
                        action="reused",
                    )
                )
                continue
            raw, prefix = generate_raw_key()
            row = ApiKeyRow(
                id=stable_uuid("digikey-key", seed, label),
                key_hash=hash_secret(raw),
                key_prefix=prefix,
                tenant_slug=tenant_slug,
                project_id=None,
                project_config_ref=None,
                scopes=list(scopes),
                kind="standard",
                label=label,
            )
            session.add(row)
            session.commit()
            minted[label] = raw
            results.append(
                KeyResult(
                    label=label,
                    key_prefix=prefix,
                    tenant_slug=tenant_slug,
                    scopes=scopes,
                    action="minted",
                    raw=raw,
                )
            )
    finally:
        session.close()

    if minted and seed_file:
        _write_secret_file(out_path, tenant_slug, minted)
    return results


def _write_secret_file(out_path: Path, tenant_slug: str, keys: dict[str, str]) -> None:
    """Write raw keys mode 0600. Never echoes a value to stdout/stderr."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = "# digithings local stack seed keys — synthetic, local digikey only.\n"
    body += f"# tenant={tenant_slug}\n"
    for label, raw in sorted(keys.items()):
        body += f"{label}={raw}\n"
    out_path.write_text(body, encoding="utf-8")
    out_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def secret_file_env(out_path: Path) -> dict[str, str]:
    """Return the `LABEL=raw` lines of a seed secret file as an env mapping."""
    if not out_path.exists():
        return {}
    env: dict[str, str] = {}
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        label, _, raw = line.partition("=")
        env[label.strip()] = raw.strip()
    return env
