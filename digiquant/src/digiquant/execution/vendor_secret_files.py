"""Load gitignored digithings vendor secret files (names-first; never log values).

After a human pastes Stripe / Mailgun / Alpaca OAuth into
``.local/secrets/digithings-{stripe,mailgun,alpaca}.env``, this module is the
resume path onto ``core`` Edge Function secrets. It reuses
:data:`KAIROS_STAGING_REQUIRED_SECRETS` so apply and staging E2E cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.kairos.staging_secrets import (
    KAIROS_STAGING_OPTIONAL_SECRETS,
    KAIROS_STAGING_REQUIRED_SECRETS,
    missing_kairos_staging_secrets,
)

EXIT_VENDOR_FILES_OR_KEYS_MISSING: int = 2
CORE_PROJECT_REF: str = "rwagjbkvxkdwqmouagad"
VENDOR_SECRETS_DIR: str = ".local/secrets"
VENDOR_SECRET_FILENAMES: tuple[str, ...] = (
    "digithings-stripe.env",
    "digithings-mailgun.env",
    "digithings-alpaca.env",
)
BILLING_FUNCTIONS: tuple[str, ...] = (
    "stripe-webhook",
    "create-checkout-session",
    "customer-portal",
    "settings",
)
WEBHOOK_FUNCTION: str = "stripe-webhook"


class VendorSecretLoad(BaseModel):
    """Sanitized load report — filenames and secret *names* only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    missing_files: tuple[str, ...] = Field(default_factory=tuple)
    missing_keys: tuple[str, ...] = Field(default_factory=tuple)
    present_files: tuple[str, ...] = Field(default_factory=tuple)
    present_key_names: tuple[str, ...] = Field(default_factory=tuple)


def vendor_secrets_dir(repo_root: Path) -> Path:
    return repo_root / VENDOR_SECRETS_DIR


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=value`` lines. Values stay in the returned dict, never logged."""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        name = key.strip()
        if not name:
            continue
        out[name] = value.strip().strip("'").strip('"')
    return out


def load_vendor_secret_environ(repo_root: Path) -> dict[str, str]:
    """Merge present vendor files. Missing files contribute nothing."""
    merged: dict[str, str] = {}
    secrets = vendor_secrets_dir(repo_root)
    for name in VENDOR_SECRET_FILENAMES:
        path = secrets / name
        if path.is_file():
            merged.update(parse_env_file(path))
    return merged


def inspect_vendor_secret_files(repo_root: Path) -> VendorSecretLoad:
    """Report missing files and missing required key *names* (never values)."""
    secrets = vendor_secrets_dir(repo_root)
    missing_files = tuple(
        name for name in VENDOR_SECRET_FILENAMES if not (secrets / name).is_file()
    )
    present_files = tuple(name for name in VENDOR_SECRET_FILENAMES if (secrets / name).is_file())
    environ = load_vendor_secret_environ(repo_root)
    missing_keys = tuple(missing_kairos_staging_secrets(environ))
    present_key_names = tuple(
        name
        for name in (*KAIROS_STAGING_REQUIRED_SECRETS, *KAIROS_STAGING_OPTIONAL_SECRETS)
        if name in environ and environ[name].strip()
    )
    return VendorSecretLoad(
        missing_files=missing_files,
        missing_keys=missing_keys,
        present_files=present_files,
        present_key_names=present_key_names,
    )


def format_vendor_apply_blocked(report: VendorSecretLoad) -> str:
    parts: list[str] = []
    if report.missing_files:
        parts.append("missing files: " + ", ".join(report.missing_files))
    if report.missing_keys:
        parts.append("missing keys: " + ", ".join(report.missing_keys))
    detail = "; ".join(parts) if parts else "unknown"
    return (
        "Kairos vendor-secret apply blocked — "
        f"{detail}. Write gitignored .local/secrets/digithings-{{stripe,mailgun,alpaca}}.env; "
        "do not fake Stripe/Mailgun/Alpaca OAuth."
    )


def write_vendor_secret_env_file(environ: Mapping[str, str], path: Path) -> None:
    """Write the selected vendor secrets to a mode-0600 CLI env file."""
    lines: list[str] = []
    for name in (*KAIROS_STAGING_REQUIRED_SECRETS, *KAIROS_STAGING_OPTIONAL_SECRETS):
        value = environ.get(name, "").strip()
        if value:
            lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def secrets_set_argv(
    env_file: Path,
    *,
    project_ref: str = CORE_PROJECT_REF,
) -> list[str]:
    """Build ``supabase secrets set`` argv without exposing values via ``ps``."""
    return [
        "npx",
        "supabase",
        "secrets",
        "set",
        f"--project-ref={project_ref}",
        f"--env-file={env_file}",
    ]


def function_deploy_argv(
    function: str,
    *,
    project_ref: str = CORE_PROJECT_REF,
) -> list[str]:
    cmd = [
        "npx",
        "supabase",
        "functions",
        "deploy",
        function,
        f"--project-ref={project_ref}",
    ]
    if function == WEBHOOK_FUNCTION:
        cmd.append("--no-verify-jwt")
    return cmd


def apply_ready(report: VendorSecretLoad) -> bool:
    return not report.missing_files and not report.missing_keys


__all__ = [
    "BILLING_FUNCTIONS",
    "CORE_PROJECT_REF",
    "EXIT_VENDOR_FILES_OR_KEYS_MISSING",
    "VENDOR_SECRET_FILENAMES",
    "VENDOR_SECRETS_DIR",
    "VendorSecretLoad",
    "apply_ready",
    "format_vendor_apply_blocked",
    "function_deploy_argv",
    "inspect_vendor_secret_files",
    "load_vendor_secret_environ",
    "parse_env_file",
    "secrets_set_argv",
    "vendor_secrets_dir",
    "write_vendor_secret_env_file",
]
