#!/usr/bin/env python3
"""WP10.2 — write-denied allocation shadow isolation checker (#2762).

Statically and behaviorally prove the shadow evaluation surface stays
artifact-in / file-out only: no production credentials, commit I/O, network
sinks, live Nautilus, or broker paths. Does not implement the challenger
optimizer (WP10.3+).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_RELPATH = Path(".github/workflows/pipeline-olympus-allocation-shadow.yml")

TRUSTED_SOURCE_WORKFLOWS: frozenset[str] = frozenset({"Pipeline: Olympus research"})
TRUSTED_SOURCE_BRANCHES: frozenset[str] = frozenset({"main"})
ALLOWED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})

# Least privilege for artifact download + checkout. No writes of any kind.
ALLOWED_TOP_LEVEL_PERMISSIONS: dict[str, str] = {
    "contents": "read",
    "actions": "read",
}

FORBIDDEN_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"secrets\s*:\s*inherit",
        r"secrets\.(CORE_)?SUPABASE",
        r"secrets\.SUPABASE",
        r"secrets\.OPENROUTER",
        r"secrets\.LANGSMITH",
        r"secrets\.DIGI_CHECKPOINTER",
        r"secrets\.[A-Z0-9_]*(BROKER|PROVIDER|API_KEY|SERVICE_ROLE|SERVICE_KEY)",
        r"\$\{\{\s*secrets\.(?!GITHUB_TOKEN\b)[A-Z0-9_]+\s*\}\}",
    )
)

FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset(
    {
        "supabase",
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "nautilus_trader",
        "digiquant.brokers",
        "digiquant.olympus.atlas.supabase_io",
        "digiquant.olympus.hermes.writers",
        "digiquant.olympus.hermes.writers.commit_io",
        "digiquant.olympus.hermes.writers.execution_io",
        "digiquant.olympus.hermes.writers.opening_snapshot",
        "digiquant.olympus.hermes.phases.h9_commit_run",
    }
)

# Surface scanned for forbidden imports when present in-tree.
# shadow_optimizer.py is the WP10.3 challenger — still write-denied / no network.
DEFAULT_SCAN_RELPATHS: tuple[str, ...] = (
    "digiquant/scripts/atlas/check_allocation_shadow_isolation.py",
    "digiquant/scripts/atlas/compare_allocation_shadow.py",
    "digiquant/src/digiquant/olympus/hermes/shadow_artifact.py",
    "digiquant/src/digiquant/olympus/hermes/shadow_optimizer.py",
    "digiquant/src/digiquant/olympus/replay/allocation_comparison.py",
)


@dataclass(frozen=True)
class IsolationFinding:
    """One isolation violation."""

    code: str
    message: str
    path: str | None = None


@dataclass
class IsolationReport:
    """File-only isolation check result."""

    ok: bool
    findings: list[IsolationFinding] = field(default_factory=list)
    checked_workflow: str | None = None
    checked_artifacts: list[str] = field(default_factory=list)
    checked_modules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [asdict(f) for f in self.findings],
            "checked_workflow": self.checked_workflow,
            "checked_artifacts": list(self.checked_artifacts),
            "checked_modules": list(self.checked_modules),
        }


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
    return imported


def _is_forbidden_import(module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES
    )


def check_forbidden_imports(*, path: Path, source: str | None = None) -> list[IsolationFinding]:
    """Reject Supabase / H9 commit I/O / network / live Nautilus / broker imports."""
    text = path.read_text(encoding="utf-8") if source is None else source
    findings: list[IsolationFinding] = []
    try:
        imported = _imported_modules(text)
    except SyntaxError as exc:
        return [
            IsolationFinding(
                code="import_parse_error",
                message=f"cannot parse Python for import scan: {exc}",
                path=str(path),
            )
        ]
    for mod in sorted(imported):
        if _is_forbidden_import(mod):
            findings.append(
                IsolationFinding(
                    code="forbidden_import",
                    message=f"forbidden import {mod!r}",
                    path=str(path),
                )
            )
    return findings


def _strip_yaml_comments(text: str) -> str:
    """Drop full-line and trailing ``#`` comments so advisory prose cannot trip scanners."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            in_single = False
            in_double = False
            cut = len(line)
            for idx, ch in enumerate(line):
                if ch == "'" and not in_double:
                    in_single = not in_single
                elif ch == '"' and not in_single:
                    in_double = not in_double
                elif ch == "#" and not in_single and not in_double:
                    cut = idx
                    break
            line = line[:cut].rstrip()
        lines.append(line)
    return "\n".join(lines) + "\n"


def check_workflow_text(text: str, *, path: str | None = None) -> list[IsolationFinding]:
    """Reject secrets, write permissions, secrets:inherit, and untrusted source gates."""
    findings: list[IsolationFinding] = []
    label = path or "<workflow>"
    scan_text = _strip_yaml_comments(text)

    for pattern in FORBIDDEN_SECRET_PATTERNS:
        if pattern.search(scan_text):
            findings.append(
                IsolationFinding(
                    code="forbidden_secret",
                    message=f"workflow matches forbidden secret pattern {pattern.pattern!r}",
                    path=label,
                )
            )

    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return [
            IsolationFinding(
                code="workflow_parse_error",
                message=f"cannot parse workflow YAML: {exc}",
                path=label,
            )
        ]

    if not isinstance(doc, dict):
        return [
            IsolationFinding(
                code="workflow_parse_error",
                message="workflow root must be a mapping",
                path=label,
            )
        ]

    if "secrets" in doc:
        findings.append(
            IsolationFinding(
                code="secrets_inherit",
                message="top-level secrets block is forbidden (no secrets: inherit / production secrets)",
                path=label,
            )
        )

    permissions = doc.get("permissions")
    if permissions is None:
        findings.append(
            IsolationFinding(
                code="missing_permissions",
                message="workflow must declare explicit least-privilege permissions",
                path=label,
            )
        )
    elif not isinstance(permissions, dict):
        findings.append(
            IsolationFinding(
                code="invalid_permissions",
                message="permissions must be a mapping of scope -> access",
                path=label,
            )
        )
    else:
        for scope, access in permissions.items():
            expected = ALLOWED_TOP_LEVEL_PERMISSIONS.get(str(scope))
            if expected is None or str(access) != expected:
                findings.append(
                    IsolationFinding(
                        code="write_permission",
                        message=(
                            f"disallowed permission {scope}: {access!r}; "
                            f"allowed only {ALLOWED_TOP_LEVEL_PERMISSIONS}"
                        ),
                        path=label,
                    )
                )
        for required_scope, required_access in ALLOWED_TOP_LEVEL_PERMISSIONS.items():
            if permissions.get(required_scope) != required_access:
                findings.append(
                    IsolationFinding(
                        code="missing_permissions",
                        message=f"workflow must set permissions.{required_scope}: {required_access}",
                        path=label,
                    )
                )

    jobs = doc.get("jobs") or {}
    if not isinstance(jobs, dict):
        findings.append(
            IsolationFinding(
                code="invalid_jobs",
                message="jobs must be a mapping",
                path=label,
            )
        )
        jobs = {}

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if "secrets" in job:
            findings.append(
                IsolationFinding(
                    code="secrets_inherit",
                    message=f"job {job_name!r} must not declare secrets (no secrets: inherit)",
                    path=label,
                )
            )
        job_perms = job.get("permissions")
        if isinstance(job_perms, dict):
            for scope, access in job_perms.items():
                if str(access).lower() != "read" and str(access).lower() != "none":
                    findings.append(
                        IsolationFinding(
                            code="write_permission",
                            message=f"job {job_name!r} has non-read permission {scope}: {access!r}",
                            path=label,
                        )
                    )

        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            env = step.get("env") or {}
            if isinstance(env, dict):
                dumped = yaml.safe_dump(env)
                for pattern in FORBIDDEN_SECRET_PATTERNS:
                    if pattern.search(dumped):
                        findings.append(
                            IsolationFinding(
                                code="forbidden_secret",
                                message=(
                                    f"job {job_name!r} step env matches forbidden secret "
                                    f"pattern {pattern.pattern!r}"
                                ),
                                path=label,
                            )
                        )

    on = doc.get("on") or doc.get(True)  # YAML may parse `on` as True
    if on is True:
        # Re-parse with Loader that preserves `on` is awkward; inspect raw text.
        on = _extract_on_block(text)

    findings.extend(_check_source_trust_gates(on, path=label))
    findings.extend(_check_file_only_output(doc, text=scan_text, path=label))
    return findings


def _extract_on_block(text: str) -> dict[str, Any]:
    """Best-effort extract of the ``on:`` mapping when PyYAML coerces the key to True."""
    match = re.search(r"(?m)^on:\s*\n((?:[ \t]+.+\n)+)", text)
    if not match:
        return {}
    try:
        loaded = yaml.safe_load("on:\n" + match.group(1)) or {}
    except yaml.YAMLError:
        return {}
    if isinstance(loaded, dict):
        return loaded.get("on") or {}
    return {}


def _check_source_trust_gates(on: Any, *, path: str) -> list[IsolationFinding]:
    findings: list[IsolationFinding] = []
    if not isinstance(on, dict):
        findings.append(
            IsolationFinding(
                code="untrusted_source",
                message="workflow trigger block missing or invalid",
                path=path,
            )
        )
        return findings

    workflow_run = on.get("workflow_run")
    if workflow_run is None:
        findings.append(
            IsolationFinding(
                code="untrusted_source",
                message="workflow must gate on workflow_run from an approved Olympus producer",
                path=path,
            )
        )
        return findings

    if isinstance(workflow_run, list):
        workflow_run = workflow_run[0] if workflow_run else {}
    if not isinstance(workflow_run, dict):
        findings.append(
            IsolationFinding(
                code="untrusted_source",
                message="workflow_run trigger must be a mapping",
                path=path,
            )
        )
        return findings

    workflows = workflow_run.get("workflows") or []
    if not isinstance(workflows, list):
        workflows = [workflows]
    trusted = [str(w) for w in workflows if str(w) in TRUSTED_SOURCE_WORKFLOWS]
    if not trusted:
        findings.append(
            IsolationFinding(
                code="untrusted_source",
                message=(
                    f"workflow_run.workflows must include one of {sorted(TRUSTED_SOURCE_WORKFLOWS)}; "
                    f"got {workflows!r}"
                ),
                path=path,
            )
        )

    branches = workflow_run.get("branches") or []
    if not isinstance(branches, list):
        branches = [branches]
    if not branches or not any(str(b) in TRUSTED_SOURCE_BRANCHES for b in branches):
        findings.append(
            IsolationFinding(
                code="untrusted_branch",
                message=(
                    f"workflow_run.branches must include a trusted branch "
                    f"{sorted(TRUSTED_SOURCE_BRANCHES)}; got {branches!r}"
                ),
                path=path,
            )
        )
    return findings


def _check_file_only_output(doc: dict[str, Any], *, text: str, path: str) -> list[IsolationFinding]:
    """Shadow job may upload local files only — no network/DB sinks in steps."""
    findings: list[IsolationFinding] = []
    sink_patterns = (
        re.compile(r"\bcurl\b", re.IGNORECASE),
        re.compile(r"\bwget\b", re.IGNORECASE),
        re.compile(r"--supabase\b"),
        re.compile(r"supabase\.com", re.IGNORECASE),
        re.compile(r"openrouter\.ai", re.IGNORECASE),
    )
    for pattern in sink_patterns:
        if pattern.search(text):
            findings.append(
                IsolationFinding(
                    code="network_sink",
                    message=f"workflow contains forbidden network/DB sink pattern {pattern.pattern!r}",
                    path=path,
                )
            )

    jobs = doc.get("jobs") or {}
    if not isinstance(jobs, dict):
        return findings

    has_upload = False
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses") or "")
            if uses.startswith("actions/upload-artifact@"):
                has_upload = True
    if not has_upload:
        findings.append(
            IsolationFinding(
                code="missing_file_output",
                message="workflow must upload a local result artifact (file-only output)",
                path=path,
            )
        )
    return findings


def check_artifact_trust(
    payload: dict[str, Any],
    *,
    path: str | None = None,
    source_workflow: str | None = None,
    source_branch: str | None = None,
    require_hash: bool = True,
) -> list[IsolationFinding]:
    """Reject untrusted schema / hash / producer identity for a shadow artifact."""
    findings: list[IsolationFinding] = []
    label = path or "<artifact>"

    if source_workflow is not None and source_workflow not in TRUSTED_SOURCE_WORKFLOWS:
        findings.append(
            IsolationFinding(
                code="untrusted_source",
                message=f"artifact source workflow {source_workflow!r} is not trusted",
                path=label,
            )
        )
    if source_branch is not None and source_branch not in TRUSTED_SOURCE_BRANCHES:
        findings.append(
            IsolationFinding(
                code="untrusted_branch",
                message=f"artifact source branch {source_branch!r} is not trusted",
                path=label,
            )
        )

    schema = str(payload.get("schema_version") or "")
    if schema not in ALLOWED_SCHEMA_VERSIONS:
        findings.append(
            IsolationFinding(
                code="untrusted_schema",
                message=f"schema_version {schema!r} not in {sorted(ALLOWED_SCHEMA_VERSIONS)}",
                path=label,
            )
        )

    content_hash = payload.get("artifact_content_hash")
    if require_hash and (not isinstance(content_hash, str) or len(content_hash) < 32):
        findings.append(
            IsolationFinding(
                code="untrusted_hash",
                message="artifact_content_hash missing or too short",
                path=label,
            )
        )

    if require_hash and isinstance(content_hash, str) and schema in ALLOWED_SCHEMA_VERSIONS:
        try:
            from digiquant.olympus.hermes.shadow_artifact import (
                ShadowAllocationArtifact,
            )

            ShadowAllocationArtifact.model_validate(payload)
        except Exception as exc:  # pydantic ValidationError or import issues
            findings.append(
                IsolationFinding(
                    code="untrusted_hash",
                    message=f"artifact failed ShadowAllocationArtifact validation: {exc}",
                    path=label,
                )
            )
    return findings


def run_isolation_checks(
    *,
    repo_root: Path = REPO_ROOT,
    workflow_path: Path | None = None,
    artifact_paths: list[Path] | None = None,
    module_paths: list[Path] | None = None,
    source_workflow: str | None = None,
    source_branch: str | None = None,
    validate_artifact_models: bool = True,
) -> IsolationReport:
    """Run workflow + import + artifact trust checks; file-only report."""
    findings: list[IsolationFinding] = []
    wf = workflow_path or (repo_root / WORKFLOW_RELPATH)
    checked_modules: list[str] = []
    checked_artifacts: list[str] = []

    if not wf.is_file():
        findings.append(
            IsolationFinding(
                code="missing_workflow",
                message=f"shadow workflow missing at {wf}",
                path=str(wf),
            )
        )
    else:
        findings.extend(check_workflow_text(wf.read_text(encoding="utf-8"), path=str(wf)))

    scan_paths = module_paths
    if scan_paths is None:
        scan_paths = [
            repo_root / rel for rel in DEFAULT_SCAN_RELPATHS if (repo_root / rel).is_file()
        ]

    for mod_path in scan_paths:
        if not mod_path.is_file():
            continue
        checked_modules.append(str(mod_path))
        findings.extend(check_forbidden_imports(path=mod_path))

    for art in artifact_paths or []:
        checked_artifacts.append(str(art))
        try:
            payload = json.loads(art.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                IsolationFinding(
                    code="artifact_read_error",
                    message=f"cannot read artifact JSON: {exc}",
                    path=str(art),
                )
            )
            continue
        if not isinstance(payload, dict):
            findings.append(
                IsolationFinding(
                    code="untrusted_schema",
                    message="artifact root must be a JSON object",
                    path=str(art),
                )
            )
            continue
        findings.extend(
            check_artifact_trust(
                payload,
                path=str(art),
                source_workflow=source_workflow,
                source_branch=source_branch,
                require_hash=validate_artifact_models,
            )
        )

    return IsolationReport(
        ok=not findings,
        findings=findings,
        checked_workflow=str(wf) if wf.is_file() else None,
        checked_artifacts=checked_artifacts,
        checked_modules=checked_modules,
    )


def write_report(report: IsolationReport, output_path: Path) -> None:
    """Persist isolation report as local JSON only (no network)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check write-denied isolation for Olympus allocation shadow evaluation."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: inferred from script location).",
    )
    parser.add_argument(
        "--workflow",
        type=Path,
        default=None,
        help="Path to pipeline-olympus-allocation-shadow.yml",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=Path,
        help="Shadow allocation artifact JSON (repeatable).",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=None,
        type=Path,
        help="Extra Python module to scan for forbidden imports (repeatable).",
    )
    parser.add_argument(
        "--source-workflow",
        default=None,
        help="Producer workflow name for artifact trust gate.",
    )
    parser.add_argument(
        "--source-branch",
        default=None,
        help="Producer branch for artifact trust gate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/allocation-shadow-isolation-report.json"),
        help="File-only isolation report path.",
    )
    parser.add_argument(
        "--skip-artifact-model-validation",
        action="store_true",
        help="Only check schema/hash presence; skip ShadowAllocationArtifact validate.",
    )
    args = parser.parse_args(argv)

    report = run_isolation_checks(
        repo_root=args.repo_root.resolve(),
        workflow_path=args.workflow.resolve() if args.workflow else None,
        artifact_paths=[p.resolve() for p in args.artifact],
        module_paths=[p.resolve() for p in args.module] if args.module is not None else None,
        source_workflow=args.source_workflow,
        source_branch=args.source_branch,
        validate_artifact_models=not args.skip_artifact_model_validation,
    )
    write_report(report, args.output.resolve())

    if report.ok:
        print(f"isolation ok — report {args.output}")
        return 0

    print(
        f"isolation FAILED ({len(report.findings)} finding(s)) — report {args.output}",
        file=sys.stderr,
    )
    for finding in report.findings:
        loc = f" [{finding.path}]" if finding.path else ""
        print(f"  - {finding.code}: {finding.message}{loc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
