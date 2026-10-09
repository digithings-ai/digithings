"""Guard: zammad_mcp renders customer data in full, with no masking layer.

Chris rejected masking on 2026-10-06 (card 34a86696, DIG-1498): the OCC
demo returns unmasked customer PII and staff internal notes. Two masking
implementations were proposed and both were closed unmerged — #5148
(``task/1063-zammad-mask-by-default``, a ``privacy.py`` module behind
``ZAMMAD_MCP_CUSTOMER_DISCLOSURE``) and #5155
(``task/1063-zammad-mask-customer-pii``, inline ``_mask_customer`` helpers
behind ``ZAMMAD_DEMO_UNMASKED_PII``).

This file pins that decision so a future masking PR fails loudly instead of
merging quietly. The two closed PRs used *different* machinery, so a scan for
one PR's symbols alone would pass vacuously on the other: the behavioural
assertions below are the load-bearing part, and the source scan is a second
line of defence with a positive control of its own.

``ruff_and_scripts`` runs ``tests/scripts/ -m "unit or baseline"`` and its path
filter covers ``tests/**``, so ``pytestmark = unit`` is what puts this file in
CI at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.zammad_mcp import formatting

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
ZAMMAD_DIR = REPO_ROOT / "scripts" / "zammad_mcp"

# The two closed masking PRs and the symbols only they introduced. Listed
# separately so a failure names the PR whose machinery came back.
MASKING_SYMBOLS: dict[str, tuple[str, ...]] = {
    # PR #5148 — scripts/zammad_mcp/privacy.py
    "PR-5148": (
        "ZAMMAD_MCP_CUSTOMER_DISCLOSURE",
        "ZAMMAD_MCP_UNMASK_APPROVER",
        "PSEUDONYM_PREFIX",
        "customer_label",
        "disclosure_mode",
        "visible_articles",
        "is_masked",
        "customer #",
    ),
    # PR #5155 — inline helpers in formatting.py
    "PR-5155": (
        "ZAMMAD_DEMO_UNMASKED_PII",
        "REDACTED_CUSTOMER",
        "customer name withheld",
        "_mask_customer",
        "_mask_contact",
    ),
}

# Every env var either masking PR consulted. The unmasked contract is that
# customer rendering does not read the environment at all, so these are
# asserted inert rather than merely unset.
MASKING_ENV_VARS = (
    "ZAMMAD_MCP_CUSTOMER_DISCLOSURE",
    "ZAMMAD_MCP_UNMASK_APPROVER",
    "ZAMMAD_DEMO_UNMASKED_PII",
)

FULL_EMAIL = "jane.doe@customer.example.test"
FULL_NAME = "Jane Doe"
FULL_CUSTOMER = f"{FULL_NAME} <{FULL_EMAIL}>"
CUSTOMER_ID = 42

TICKET = {
    "id": 231,
    "number": "28312",
    "title": "Example ticket subject",
    "state": "open",
    "group": "Sitaas",
    "priority": "2 normal",
    "customer": FULL_EMAIL,
    "owner": "11111111-1111-1111-1111-111111111111",
    "updated_at": "2026-09-15T12:00:00.000Z",
}

ARTICLES = [
    {
        "sender": "Customer",
        "type": "web",
        "internal": False,
        "from": FULL_CUSTOMER,
        "subject": "Cannot log in",
        "body": "<p>My password reset never arrives.</p>",
        "created_at": "2026-09-15T09:00:00.000Z",
    },
    {
        "sender": "Agent",
        "type": "note",
        "internal": True,
        "from": "agent.lead@sitaas.de",
        "subject": "Internal triage",
        "body": "<p>Account flagged after three failed payments.</p>",
        "created_at": "2026-09-15T10:00:00.000Z",
    },
]


@pytest.fixture(autouse=True)
def _no_masking_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear every masking env var so the assertions below are about code, not config.

    A masking PR that defaulted to masked would otherwise pass CI on a machine
    that happened to export the unmask override — the same shape as a 200 that
    is byte-identical to the no-credential baseline.
    """
    for name in MASKING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# Behavioural contract. These are what actually broke under #5148 and #5155.
# --------------------------------------------------------------------------


def test_ticket_line_shows_the_full_customer_email() -> None:
    line = formatting.format_ticket_line(dict(TICKET))

    assert f"customer: {FULL_EMAIL}" in line
    # The masked rendering (#5155) was "j***@customer.example.test".
    assert "j***@" not in line


def test_ticket_detail_returns_internal_articles() -> None:
    detail = formatting.format_ticket_detail(dict(TICKET), [dict(a) for a in ARTICLES])

    assert "[internal]" in detail
    assert "Internal triage" in detail
    assert "Account flagged after three failed payments." in detail
    assert f"Articles ({len(ARTICLES)})" in detail
    # #5155 filtered internal articles out by default and footnoted the count.
    assert "omitted" not in detail


def test_ticket_detail_shows_the_full_customer_identity() -> None:
    detail = formatting.format_ticket_detail(dict(TICKET), [dict(a) for a in ARTICLES])

    assert f"Customer: {FULL_EMAIL}" in detail
    # #5148 replaced the identity with a pseudonym, "customer #42".
    assert "customer #" not in detail


def test_aggregate_customer_ranking_shows_the_full_name_and_email() -> None:
    enriched = f"{FULL_CUSTOMER} (id {CUSTOMER_ID})"
    rendered = formatting.format_aggregate(
        [{"value": str(CUSTOMER_ID), "name": enriched, "count": 3}],
        group_by="customer",
        metric="count",
        total=3,
    )

    assert enriched in rendered
    assert FULL_EMAIL in rendered
    assert FULL_NAME in rendered
    assert "customer #" not in rendered
    assert "customer name withheld" not in rendered


def test_customer_rendering_ignores_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unmasked contract has no env gate, in either direction.

    #5155 masked by default and restored full output only when
    ZAMMAD_DEMO_UNMASKED_PII was truthy. Asserting the unset case alone would
    let that design pass a green CI whenever the override happened to be
    exported. The unmasked output must therefore be identical with the vars
    absent, set to their unmask value, and set to nonsense.
    """
    baseline = (
        formatting.format_ticket_line(dict(TICKET)),
        formatting.format_ticket_detail(dict(TICKET), [dict(a) for a in ARTICLES]),
    )

    for value in ("1", "unmasked", "true", ""):
        for name in MASKING_ENV_VARS:
            monkeypatch.setenv(name, value)
        assert (
            formatting.format_ticket_line(dict(TICKET)),
            formatting.format_ticket_detail(dict(TICKET), [dict(a) for a in ARTICLES]),
        ) == baseline, f"customer rendering changed when {MASKING_ENV_VARS}={value!r}"


def test_zammad_mcp_reads_no_masking_environment_variable() -> None:
    """No module under scripts/zammad_mcp reads a masking env var at all."""
    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)}:{line_no}"
        for path in sorted(ZAMMAD_DIR.rglob("*.py"))
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if any(name in line for name in MASKING_ENV_VARS)
    )

    assert not offenders, f"masking env var read under scripts/zammad_mcp: {offenders}"


# --------------------------------------------------------------------------
# Source scan. Second line of defence, with its own positive control so an
# empty result cannot be mistaken for a clean scan.
# --------------------------------------------------------------------------


def _scan(text: str, symbols: tuple[str, ...]) -> list[str]:
    return [symbol for symbol in symbols if symbol in text]


def _zammad_sources() -> dict[str, str]:
    """Every Python file in the package, by repo-relative path.

    Scoped to ``.py`` because the README is *supposed* to name the rejected
    PRs and their env vars when documenting why masking is absent. Measured on
    both closed PRs, README.md was the only non-``.py`` file carrying any
    masking symbol (6 hits on #5148, 7 on #5155) — no Dockerfile or config
    did — so the executable scan loses no detection power.
    """
    return {
        str(path.relative_to(REPO_ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(ZAMMAD_DIR.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def test_source_scan_detects_masking_symbols_in_synthetic_input() -> None:
    """Positive control: the scan must fire on both closed PRs' real markers.

    Without this, "no masking symbols found" could mean "the scanner reads
    nothing" — an empty file passes as clean.
    """
    pr_5148 = (
        'DISCLOSURE_ENV = "ZAMMAD_MCP_CUSTOMER_DISCLOSURE"\n'
        'PSEUDONYM_PREFIX = "customer #"\n'
        "def customer_label(value): ...\n"
    )
    pr_5155 = (
        'UNMASKED_PII_ENV = "ZAMMAD_DEMO_UNMASKED_PII"\n'
        'REDACTED_CUSTOMER = "[customer name withheld]"\n'
        "def _mask_customer(value): ...\n"
    )

    assert _scan(pr_5148, MASKING_SYMBOLS["PR-5148"]), "scan missed PR #5148 markers"
    assert _scan(pr_5155, MASKING_SYMBOLS["PR-5155"]), "scan missed PR #5155 markers"
    assert not _scan("# clean module\n", tuple(MASKING_SYMBOLS["PR-5148"]))


def test_no_masking_symbols_under_scripts_zammad_mcp() -> None:
    sources = _zammad_sources()
    on_disk = {
        str(path.relative_to(REPO_ROOT))
        for path in ZAMMAD_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    }

    # The scan must actually have read the whole package. Asserting a count
    # would rot the next time a file is added; equality cannot pass silently.
    assert sources.keys() == on_disk, f"scan missed {sorted(on_disk - sources.keys())}"
    assert "scripts/zammad_mcp/formatting.py" in sources

    found = {
        pr: sorted(
            {f"{name}: {symbol}" for name, text in sources.items() for symbol in _scan(text, symbols)}
        )
        for pr, symbols in MASKING_SYMBOLS.items()
    }

    assert not found["PR-5148"], f"PR #5148 masking machinery is back: {found['PR-5148']}"
    assert not found["PR-5155"], f"PR #5155 masking machinery is back: {found['PR-5155']}"


def test_no_masking_symbols_in_package_docs_or_config() -> None:
    """Masking helpers must not reappear outside Python either.

    #5148 moved env wiring into the image, so ``.py``-only scanning is not
    sufficient on its own. The README is the one deliberate exception: it
    names the rejected PRs to explain why masking is absent. Everything else
    under the package must be clean.
    """
    offenders = []
    for path in sorted(ZAMMAD_DIR.rglob("*")):
        if not path.is_file() or path.suffix == ".py" or "__pycache__" in path.parts:
            continue
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pr, symbols in MASKING_SYMBOLS.items():
            for symbol in _scan(text, symbols):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pr} {symbol}")

    assert not offenders, f"masking machinery in a non-Python package file: {sorted(offenders)}"


def test_no_privacy_module_or_disclosure_doc_remain() -> None:
    """#5148 added scripts/zammad_mcp/privacy.py and a disclosure runbook."""
    stray_files = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in REPO_ROOT.glob("**/privacy.py")
        if "zammad" in str(path).lower()
    )
    stray_files += sorted(
        str(path.relative_to(REPO_ROOT))
        for path in REPO_ROOT.glob("**/*ZAMMAD_MCP_CUSTOMER_DISCLOSURE*")
    )

    assert not stray_files, f"masking artifacts from #5148 are back: {stray_files}"


def test_display_customer_returns_the_raw_value() -> None:
    """formatting._display_customer is the unmasked customer accessor."""
    assert formatting._display_customer(FULL_EMAIL) == FULL_EMAIL
    assert formatting._display_customer({"email": FULL_EMAIL}) == FULL_EMAIL
    assert formatting._display_customer({"email": ""}) == ""
