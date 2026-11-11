"""digikey CLI --tenant guard (#2303).

argparse's required=True only demands the flag be present, not non-empty — an
operator could otherwise mint a validly-signed token with an empty
tenant_slug via `--tenant ""`. Reject that at parse time instead.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.parametrize("tenant", ["", "   "])
def test_empty_tenant_is_rejected(monkeypatch, capsys, tenant):
    from digikey.cli import main

    monkeypatch.setattr("sys.argv", ["digikey", "issue-key", "--tenant", tenant])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2
    assert "--tenant must not be empty" in capsys.readouterr().err


@pytest.mark.unit
def test_default_scopes_are_not_the_wildcard() -> None:
    """#6648: a key minted without --scopes must not carry ``*``."""
    from digikey.cli import DEFAULT_ISSUE_KEY_SCOPES, _build_parser, resolve_issue_key_scopes

    args = _build_parser().parse_args(["issue-key", "--tenant", "t"])
    assert args.scopes is None
    scopes = resolve_issue_key_scopes(args.scopes, args.kind)
    assert scopes == list(DEFAULT_ISSUE_KEY_SCOPES)
    assert "*" not in scopes
    assert not any(s.startswith("mcp") for s in scopes)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    [
        ("*", "standard", ["*"]),
        (" mcp:digivault , digisearch:query ", "standard", ["mcp:digivault", "digisearch:query"]),
        (None, "dev_global", ["*"]),
        ("", "dev_global", ["*"]),
        ("", "standard", []),
    ],
)
def test_explicit_scopes_are_kept(raw, kind, expected) -> None:
    from digikey.cli import resolve_issue_key_scopes

    assert resolve_issue_key_scopes(raw, kind) == expected


@pytest.mark.unit
def test_blank_scopes_are_rejected(monkeypatch, capsys) -> None:
    from digikey.cli import main

    monkeypatch.setattr("sys.argv", ["digikey", "issue-key", "--tenant", "t", "--scopes", " "])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2
    assert "--scopes must name at least one scope" in capsys.readouterr().err
