#!/usr/bin/env python3
"""``make vault-check`` — lint the DigiVault-managed ``docs/vision`` vault.

Validates wikilink integrity, required frontmatter, the tag taxonomy, and orphans
against ``docs/vision/.digivault.yml`` using the DigiVault core (pydantic + pyyaml
only — no service extra). Exits non-zero on any issue so CI gates the docs vault,
matching the DigiVault roadmap ("make vault-check validating wikilinks and
frontmatter in CI").

Run::

    PYTHONPATH=digivault/src python3 -P scripts/check_vault.py [VAULT_DIR]
"""

from __future__ import annotations

import sys

from digivault import Vault

DEFAULT_VAULT = "docs/vision"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    vault_dir = args[0] if args else DEFAULT_VAULT

    report = Vault(vault_dir).lint()
    for issue in report.issues:
        print(f"{issue.note}: {issue.kind}: {issue.message}", file=sys.stderr)

    status = "OK" if report.ok else "FAIL"
    print(f"{status}: {vault_dir} — {report.note_count} notes, {len(report.issues)} issue(s)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
