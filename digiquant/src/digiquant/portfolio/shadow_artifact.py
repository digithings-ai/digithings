"""WP10.1 — immutable shadow allocation artifact (#2758).

One-way data boundary from a completed H9 state to an isolated challenger
workflow. Production commits once; export failure must never rerun or modify
H8/H9. This module must not import challenger optimizer, portfolio replay,
broker, or live-trading surfaces.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Annotated,
    Any,
    TypeAlias,
)

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.dashboard.envcompat import SHADOW_ARTIFACT_DIR, SHADOW_ARTIFACT_MODE, env_lookup
from digiquant.portfolio.allocation_contracts import (
    AllocationInputBundle,
    BookWeightsView,
    PreTradeRiskReport,
)
from digiquant.portfolio.allocation_hashes import (
    canonical_json,
    shadow_allocation_artifact_content_hash,
    shadow_allocation_artifact_hash_payload,
)

_logger = logging.getLogger(__name__)

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]

# Static import fence — AST tests assert these prefixes never appear here or in
# the production chain export wiring. WP10.2+/10.3 modules stay unreachable.
FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset(
    {
        "digiquant.portfolio.shadow_optimizer",
        "digiquant.dashboard.replay",
        "digiquant.brokers",
        "nautilus_trader",
    }
)

_FORBIDDEN_PAYLOAD_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "credential",
        "private_key",
        "access_token",
        "client_secret",
        "prompt",
        "system_prompt",
        "supabase_key",
        "service_role",
    }
)

_SHADOW_ARTIFACT_MODE_ENV = SHADOW_ARTIFACT_MODE
_SHADOW_ARTIFACT_DIR_ENV = SHADOW_ARTIFACT_DIR
_DEFAULT_ARTIFACT_DIR = "artifacts"


class ShadowArtifactMode(StrEnum):
    """Rollout knob for post-H9 shadow artifact export (#2758 / WP10.1).

    ``off`` — skip export entirely.
    ``export`` — write one verifiable artifact when eligible (default).
    """

    OFF = "off"
    EXPORT = "export"


class ShadowContractModel(BaseModel):
    """Strict immutable base for shadow allocation artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ShadowCommitMetadata(ShadowContractModel):
    """Minimal H9 commit identity — no clients, secrets, or prose."""

    commit_id: NonEmptyId | None = None
    commit_status: NonEmptyId
    weights_fingerprint: NonEmptyId
    source_run_id: NonEmptyId | None = None


class ShadowAllocationArtifact(ShadowContractModel):
    """Exact H8/H9 allocation inputs, incumbent book, and risk report for shadow.

    Nested bundle/report remain fully validated. Artifact identity is the SHA-256
    of metadata + nested content hashes — never Python ``hash()``.
    """

    schema_version: str = "1.0"
    run_id: NonEmptyId
    session_date: date
    commit: ShadowCommitMetadata
    allocation_input_bundle: AllocationInputBundle
    pre_trade_risk_report: PreTradeRiskReport
    incumbent_final_weights: BookWeightsView
    artifact_content_hash: NonEmptyId

    @model_validator(mode="after")
    def _validate_artifact(self) -> ShadowAllocationArtifact:
        bundle_hash = self.allocation_input_bundle.bundle_content_hash
        report = self.pre_trade_risk_report
        if report.allocation_input_bundle_hash != bundle_hash:
            raise ValueError("pre_trade_risk_report must bind allocation_input_bundle hash")
        if report.run_id != self.run_id:
            raise ValueError("pre_trade_risk_report.run_id must match artifact run_id")
        if report.session_date != self.session_date:
            raise ValueError("pre_trade_risk_report.session_date must match artifact session_date")
        if (
            self.incumbent_final_weights.weights_fingerprint
            != report.final_book_weights_fingerprint
        ):
            raise ValueError("incumbent_final_weights must match report final-book fingerprint")
        if self.commit.weights_fingerprint != report.final_book_weights_fingerprint:
            raise ValueError("commit.weights_fingerprint must match report final-book fingerprint")

        expected = shadow_allocation_artifact_content_hash(payload=self._hash_payload())
        if self.artifact_content_hash != expected:
            raise ValueError("artifact_content_hash must match canonical artifact digest")

        _assert_no_forbidden_payload_keys(self.model_dump(mode="json"))
        return self

    def _hash_payload(self) -> dict[str, object]:
        return shadow_allocation_artifact_hash_payload(
            schema_version=self.schema_version,
            run_id=self.run_id,
            session_date=self.session_date.isoformat(),
            commit_id=self.commit.commit_id,
            commit_status=self.commit.commit_status,
            allocation_input_bundle_hash=self.allocation_input_bundle.bundle_content_hash,
            pre_trade_risk_report_hash=self.pre_trade_risk_report.report_content_hash,
            incumbent_final_weights_fingerprint=(self.incumbent_final_weights.weights_fingerprint),
        )


def resolve_shadow_artifact_mode() -> ShadowArtifactMode:
    """Read ``OLYMPUS_SHADOW_ARTIFACT_MODE``; unknown values fall back to export."""
    raw = (
        env_lookup(_SHADOW_ARTIFACT_MODE_ENV, default=ShadowArtifactMode.EXPORT.value)
        .strip()
        .lower()
    )
    try:
        return ShadowArtifactMode(raw)
    except ValueError:
        _logger.warning(
            "%s=%r is not a known mode; falling back to export",
            _SHADOW_ARTIFACT_MODE_ENV,
            raw,
        )
        return ShadowArtifactMode.EXPORT


def resolve_shadow_artifact_dir() -> Path:
    """Directory for shadow JSON files (default ``artifacts/``)."""
    raw = env_lookup(_SHADOW_ARTIFACT_DIR_ENV, default=_DEFAULT_ARTIFACT_DIR).strip()
    return Path(raw or _DEFAULT_ARTIFACT_DIR)


def build_shadow_allocation_artifact(
    *,
    run_id: str,
    session_date: date,
    allocation_input_bundle: AllocationInputBundle,
    pre_trade_risk_report: PreTradeRiskReport,
    incumbent_final_weights: BookWeightsView,
    commit: ShadowCommitMetadata,
) -> ShadowAllocationArtifact:
    """Construct a validated immutable shadow artifact."""
    draft = ShadowAllocationArtifact.model_construct(
        schema_version="1.0",
        run_id=run_id,
        session_date=session_date,
        commit=commit,
        allocation_input_bundle=allocation_input_bundle,
        pre_trade_risk_report=pre_trade_risk_report,
        incumbent_final_weights=incumbent_final_weights,
        artifact_content_hash="",
    )
    digest = shadow_allocation_artifact_content_hash(payload=draft._hash_payload())
    return ShadowAllocationArtifact.model_validate(
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "session_date": session_date,
            "commit": commit,
            "allocation_input_bundle": allocation_input_bundle,
            "pre_trade_risk_report": pre_trade_risk_report,
            "incumbent_final_weights": incumbent_final_weights,
            "artifact_content_hash": digest,
        }
    )


def artifact_canonical_bytes(artifact: ShadowAllocationArtifact) -> bytes:
    """Canonical UTF-8 JSON bytes for atomic write and tamper checks."""
    return canonical_json(artifact.model_dump(mode="json")).encode("utf-8")


def write_shadow_artifact_atomic(
    path: Path | str,
    artifact: ShadowAllocationArtifact,
) -> Path:
    """Atomically replace ``path`` with canonical artifact bytes (temp + os.replace)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = artifact_canonical_bytes(artifact)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".tmp",
        dir=str(dest.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return dest


def load_shadow_artifact(path: Path | str) -> ShadowAllocationArtifact:
    """Load and re-validate an artifact; rejects tampered or incomplete files."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("shadow artifact must be a JSON object")
    return ShadowAllocationArtifact.model_validate(raw)


def shadow_artifact_filename(*, session_date: date, run_id: str) -> str:
    """Stable filesystem name for one production-shadow run."""
    safe_run = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in run_id)
    return f"shadow-allocation-{session_date.isoformat()}-{safe_run}.json"


def build_shadow_artifact_from_state(state: Any) -> ShadowAllocationArtifact | None:
    """Build from completed portfolio state, or ``None`` when ineligible.

    Never raises for missing slots — callers treat ``None`` as skip.
    """
    phase = getattr(state, "phase_portfolio", None)
    if phase is None and isinstance(state, dict):
        phase = state.get("phase_portfolio")
    if phase is None:
        return None

    bundle_raw = getattr(phase, "allocation_input_bundle", None)
    report_raw = getattr(phase, "pre_trade_risk_report", None)
    manifest = getattr(phase, "commit_manifest", None)
    if bundle_raw is None or report_raw is None or not isinstance(manifest, dict):
        return None

    status = str(manifest.get("status") or "").strip()
    if status not in {"committed", "noop"}:
        return None

    run_id = str(getattr(state, "run_id", "") or manifest.get("source_run_id") or "").strip()
    session_date = getattr(state, "run_date", None)
    if not run_id or not isinstance(session_date, date):
        return None

    try:
        bundle = AllocationInputBundle.model_validate(bundle_raw)
        report = PreTradeRiskReport.model_validate(report_raw)
        incumbent = report.final_weights
        commit = ShadowCommitMetadata(
            commit_id=_optional_nonempty(manifest.get("ledger_commit_id")),
            commit_status=status,
            weights_fingerprint=str(manifest.get("weights_fingerprint") or ""),
            source_run_id=_optional_nonempty(manifest.get("source_run_id")),
        )
        return build_shadow_allocation_artifact(
            run_id=run_id,
            session_date=session_date,
            allocation_input_bundle=bundle,
            pre_trade_risk_report=report,
            incumbent_final_weights=incumbent,
            commit=commit,
        )
    except Exception:
        _logger.exception("shadow artifact: failed to build from completed state")
        return None


def maybe_export_shadow_allocation_artifact(state: Any) -> str | None:
    """Fail-soft export after H9. Never reruns or mutates production booking.

    Returns the artifact content hash when written, else ``None``.
    """
    if resolve_shadow_artifact_mode() is ShadowArtifactMode.OFF:
        return None
    try:
        artifact = build_shadow_artifact_from_state(state)
        if artifact is None:
            return None
        dest = resolve_shadow_artifact_dir() / shadow_artifact_filename(
            session_date=artifact.session_date,
            run_id=artifact.run_id,
        )
        write_shadow_artifact_atomic(dest, artifact)
        _logger.info(
            "shadow artifact: exported hash=%s path=%s",
            artifact.artifact_content_hash,
            dest,
        )
        return artifact.artifact_content_hash
    except Exception:
        # Production result remains committed once — export is observational.
        _logger.exception("shadow artifact: export failed; production commit unchanged")
        return None


def _optional_nonempty(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _assert_no_forbidden_payload_keys(payload: object, *, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            for fragment in _FORBIDDEN_PAYLOAD_KEY_FRAGMENTS:
                if fragment in key_l:
                    raise ValueError(f"forbidden key {key!r} at {path}")
            _assert_no_forbidden_payload_keys(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            _assert_no_forbidden_payload_keys(item, path=f"{path}[{idx}]")


__all__ = [
    "FORBIDDEN_IMPORT_PREFIXES",
    "ShadowAllocationArtifact",
    "ShadowArtifactMode",
    "ShadowCommitMetadata",
    "artifact_canonical_bytes",
    "build_shadow_allocation_artifact",
    "build_shadow_artifact_from_state",
    "load_shadow_artifact",
    "maybe_export_shadow_allocation_artifact",
    "resolve_shadow_artifact_dir",
    "resolve_shadow_artifact_mode",
    "shadow_artifact_filename",
    "write_shadow_artifact_atomic",
]
