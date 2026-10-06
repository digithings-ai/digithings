#!/usr/bin/env python3
"""Fail-loud staleness detector for the digichat Container App inline secrets.

Why this exists
---------------
`datatap-rg/digichat` and `datatap-dev-rg/digichat` each declare two secrets with
inline values (`auth-secret`, `embed-tenants`) and `keyVaultUrl: null`. There is no
Key Vault in the DataTap subscription, so the Container App *is* the canonical store:
one copy, no second copy to drift. That makes silent change the only real failure
mode -- a secret can be replaced on the app, or drift between prod and dev, and
nothing in the repo notices because no value is stored anywhere to compare against.

This detector closes that hole without ever storing a secret:

* `docs/ops/digichat-aca-secret-fingerprints.json` records a SHA-256 and a byte
  length per binding. Both are safe to commit; neither is the value.
* The detector reads each live value **inside this process only** through
  `az containerapp secret list --show-values`, hashes it, and compares. The value
  is never printed, never returned, never written to disk, never passed to an LLM.

What it fails on (any of these is exit 1):

- `drift`          live fingerprint does not match the recorded one
- `missing`        the secret name is gone from the app
- `unreadable`     the subscription cannot list the secret at all (infra, not drift)
- `migrated`       the binding now points at a Key Vault -- the durable answer was
                   taken, so the fingerprint row is stale and must be deleted
- `unbound`        the env var no longer references the secret by name
- `unrecorded`     the app carries a secret that has no owner or fingerprint in the
                   lock -- the exact gap this detector exists to close
- `expired`        past the recorded expiry date; re-verify, rotate, or re-decide
- `lock`           the lock file itself is malformed or incomplete

Usage
-----
    python scripts/digichat_aca_secret_detector.py                # live, read-only
    python scripts/digichat_aca_secret_detector.py --offline      # no `az` call
    python scripts/digichat_aca_secret_detector.py --json         # machine output
    python scripts/digichat_aca_secret_detector.py --today 2027-02-01

Exit codes: 0 = every check passed, 1 = a finding, 2 = bad input or `az` unavailable.

`--offline` is the CI-safe mode: it validates the lock file and the expiry only, so
it can run in a workflow with no Azure credentials at all.

Rotate with `az containerapp secret set` on **one** app at a time, then re-run this
to record the new fingerprint. Never pass `--secrets` to `az containerapp update` --
see `docs/ops/digichat-datatap-aca.md` section 4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = REPO_ROOT / "docs" / "ops" / "digichat-aca-secret-fingerprints.json"

FAIL = "FAIL"
OK = "OK"


@dataclass
class Finding:
    level: str
    code: str
    subject: str
    detail: str

    def render(self) -> str:
        return f"{self.level:<4} {self.code:<10} {self.subject}\n          {self.detail}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, code: str, subject: str, detail: str) -> None:
        self.findings.append(Finding(level, code, subject, detail))

    def ok(self, code: str, subject: str, detail: str) -> None:
        self.add(OK, code, subject, detail)

    @property
    def failed(self) -> list[Finding]:
        return [f for f in self.findings if f.level == FAIL]

    def as_json(self) -> dict[str, Any]:
        return {
            "status": "fail" if self.failed else "pass",
            "checks": [
                {"level": f.level, "code": f.code, "subject": f.subject, "detail": f.detail}
                for f in self.findings
            ],
        }


class InfraError(RuntimeError):
    """`az` is missing, unauthenticated, or refused the call. Not a credential finding."""


# --------------------------------------------------------------------------- helpers


def _subject(binding: dict[str, Any]) -> str:
    return f"{binding.get('resource_group', '?')}/{binding.get('secret_name', '?')}"


def _is_hex_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(c in "0123456789abcdef" for c in value.lower())


def _fingerprint(value: str) -> tuple[str, int]:
    """Hash a secret inside this process. The value must not leave this function."""
    raw = value.encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _run_az(az_bin: str, args: list[str], what: str) -> str:
    exe = shutil.which(az_bin) or (az_bin if Path(az_bin).exists() else None)
    if exe is None:
        raise InfraError(f"az binary not found: {az_bin!r}")
    try:
        proc = subprocess.run(
            [exe, *args], capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env dependent
        raise InfraError(f"could not run az for {what}: {exc}") from exc
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        tail = stderr[-1] if stderr else f"exit {proc.returncode}"
        raise InfraError(f"az refused {what}: {tail}")
    # `az ... -o tsv` appends exactly one newline. Strip that one, never more.
    out = proc.stdout
    if out.endswith("\n"):
        out = out[:-1]
    return out


# --------------------------------------------------------------------------- checks


def check_lock_shape(lock: dict[str, Any], report: Report) -> bool:
    """Validate everything the offline mode can validate. Returns True if usable."""
    usable = True
    bindings = lock.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        report.add(FAIL, "lock", "bindings", "no bindings list in the lock file")
        return False

    seen: set[tuple[str, str]] = set()
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            report.add(FAIL, "lock", f"bindings[{index}]", "entry is not an object")
            usable = False
            continue
        subject = _subject(binding)
        missing = [
            key
            for key in ("resource_group", "secret_name", "env_var", "sha256", "owner", "canonical_store")
            if not binding.get(key)
        ]
        if missing:
            report.add(FAIL, "lock", subject, f"missing field(s): {', '.join(missing)}")
            usable = False
        if not _is_hex_sha256(binding.get("sha256")):
            report.add(FAIL, "lock", subject, "sha256 is not 64 hex characters")
            usable = False
        length = binding.get("length_bytes")
        if not isinstance(length, int) or length <= 0:
            report.add(FAIL, "lock", subject, f"length_bytes is not a positive integer: {length!r}")
            usable = False
        key = (str(binding.get("resource_group")), str(binding.get("secret_name")))
        if key in seen:
            report.add(FAIL, "lock", subject, "duplicate resource_group + secret_name binding")
            usable = False
        seen.add(key)

    if usable:
        report.ok("lock", f"{len(bindings)} bindings", "schema, fingerprints and owners are complete")
    return usable


def check_expiry(lock: dict[str, Any], today: date, report: Report) -> None:
    expiry = _parse_iso_date(lock.get("expiry"))
    if expiry is None:
        report.add(
            FAIL,
            "lock",
            "expiry",
            f"no parseable expiry in the lock file: {lock.get('expiry')!r}",
        )
        return
    if today > expiry:
        report.add(
            FAIL,
            "expired",
            "inventory",
            f"expiry {expiry.isoformat()} is in the past (today {today.isoformat()}). "
            "Re-verify, rotate, or re-decide the store, then bump `expiry`.",
        )
    else:
        remaining = (expiry - today).days
        report.ok("expiry", f"expires {expiry.isoformat()}", f"{remaining} day(s) left")


def check_env_bindings(az_bin: str, lock: dict[str, Any], bindings: Iterable[dict[str, Any]],
                       report: Report) -> None:
    """Assert each secret is still declared inline and still bound to its env var."""
    app = lock.get("container_app", "digichat")
    query = (
        "properties.template.containers[].env[].{env:name,secretRef:secretRef,keyVaultUrl:keyVaultUrl}"
    )
    by_group: dict[str, list[dict[str, Any]]] = {}
    for binding in bindings:
        by_group.setdefault(str(binding["resource_group"]), []).append(binding)

    for group, group_bindings in sorted(by_group.items()):
        try:
            raw = _run_az(
                az_bin,
                ["containerapp", "show", "-n", app, "-g", group, "--query", query, "-o", "json"],
                f"az containerapp show -g {group}",
            )
        except InfraError as exc:
            report.add(FAIL, "unreadable", f"{group}/{app}", str(exc))
            continue
        try:
            env_entries = json.loads(raw)
        except json.JSONDecodeError as exc:
            report.add(FAIL, "unreadable", f"{group}/{app}", f"az returned unparseable JSON: {exc}")
            continue

        by_ref: dict[str, list[dict[str, Any]]] = {}
        for entry in env_entries:
            ref = entry.get("secretRef")
            if ref:
                by_ref.setdefault(str(ref), []).append(entry)

        for binding in group_bindings:
            subject = _subject(binding)
            entries = by_ref.get(str(binding["secret_name"]), [])
            if not entries:
                report.add(
                    FAIL,
                    "unbound",
                    subject,
                    f"no env entry references secretRef {binding['secret_name']!r} on {group}/{app}. "
                    "The secret may have been deleted, or the binding renamed.",
                )
                continue
            hit = next(
                (e for e in entries if e.get("env") == binding["env_var"]),
                None,
            )
            if hit is None:
                names = ", ".join(sorted(str(e.get("env")) for e in entries))
                report.add(
                    FAIL,
                    "unbound",
                    subject,
                    f"secretRef {binding['secret_name']!r} is bound to {names}, "
                    f"not to {binding['env_var']!r}.",
                )
                continue
            if hit.get("keyVaultUrl"):
                report.add(
                    FAIL,
                    "migrated",
                    subject,
                    "the binding now resolves through a Key Vault. That is the durable answer. "
                    "Delete this fingerprint row from the lock file and point the canonical store "
                    "at the vault -- a fingerprint of an inline value is stale by definition.",
                )
                continue
            report.ok("inline", subject, f"bound to {binding['env_var']} with an inline value (keyVaultUrl null)")

        recorded = {str(b["secret_name"]) for b in group_bindings}
        for ref in sorted(set(by_ref) - recorded):
            names = ", ".join(sorted(str(e.get("env")) for e in by_ref[ref]))
            report.add(
                FAIL,
                "unrecorded",
                f"{group}/{ref}",
                f"secretRef {ref!r} is bound to {names} but has no row in the lock file, so it "
                "has no owner, no fingerprint and no detector coverage. Record it, or remove it "
                "from the app.",
            )


def check_fingerprints(az_bin: str, lock: dict[str, Any], bindings: Iterable[dict[str, Any]],
                       report: Report) -> None:
    """Compare each live value's hash against the lock. The value never escapes."""
    app = lock.get("container_app", "digichat")
    for binding in bindings:
        subject = _subject(binding)
        name = str(binding["secret_name"])
        group = str(binding["resource_group"])
        try:
            value = _run_az(
                az_bin,
                [
                    "containerapp", "secret", "list",
                    "-n", app, "-g", group,
                    "--show-values",
                    "--query", f"[?name=='{name}'].value | [0]",
                    "-o", "tsv",
                ],
                f"az containerapp secret list -g {group}",
            )
        except InfraError as exc:
            report.add(FAIL, "unreadable", subject, str(exc))
            continue
        if value in ("", "None", "null"):
            report.add(
                FAIL,
                "missing",
                subject,
                f"the app declares no secret named {name!r} (or it has no value).",
            )
            continue
        actual_sha, actual_len = _fingerprint(value)
        del value  # do not keep the secret alive any longer than needed
        expected_sha = str(binding["sha256"]).lower()
        expected_len = binding["length_bytes"]
        if actual_sha == expected_sha and actual_len == expected_len:
            report.ok("fingerprint", subject, f"matches the recorded fingerprint ({actual_len} bytes)")
            continue
        report.add(
            FAIL,
            "drift",
            subject,
            f"live value no longer matches the record. recorded sha256={expected_sha} "
            f"len={expected_len} bytes; live sha256={actual_sha} len={actual_len} bytes. "
            "If this was a deliberate rotation, update the lock file. If it was not, the secret "
            "changed outside the inventory -- treat it as an incident.",
        )


# --------------------------------------------------------------------------- driver


def load_lock(path: Path) -> dict[str, Any]:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InfraError(f"lock file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InfraError(f"lock file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(lock, dict):
        raise InfraError(f"lock file must be a JSON object: {path}")
    return lock


def run(lock_path: Path, offline: bool, today: date, az_bin: str) -> Report:
    report = Report()
    lock = load_lock(lock_path)
    check_expiry(lock, today, report)
    if not check_lock_shape(lock, report):
        return report
    if offline:
        report.ok("offline", "azure", "skipped the live read by request (--offline)")
        return report
    bindings = lock["bindings"]
    check_env_bindings(az_bin, lock, bindings, report)
    check_fingerprints(az_bin, lock, bindings, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-loud staleness detector for the digichat ACA inline secrets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit 0 = clean, 1 = a finding, 2 = bad input or az unavailable.",
    )
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK, help="path to the fingerprint lock file")
    parser.add_argument("--offline", action="store_true", help="validate the lock and expiry only; never call az")
    parser.add_argument("--today", type=str, default=None, help="override today's date (YYYY-MM-DD) for expiry maths")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit machine-readable output")
    parser.add_argument(
        "--az-bin",
        default=os.environ.get("AZURE_CLI", "az"),
        help="azure CLI to call (default: $AZURE_CLI or az)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.today:
        parsed = _parse_iso_date(args.today)
        if parsed is None:
            print(f"--today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
            return 2
        today = parsed
    else:
        today = date.today()

    try:
        report = run(args.lock, args.offline, today, args.az_bin)
    except InfraError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(report.as_json(), indent=2, sort_keys=True))
    else:
        for finding in report.findings:
            print(finding.render())
        failed = report.failed
        if failed:
            print(f"\n{len(failed)} finding(s). The digichat secret inventory is not trustworthy right now.")
        else:
            print("\nAll checks passed. digichat ACA inline secrets match the recorded inventory.")

    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())