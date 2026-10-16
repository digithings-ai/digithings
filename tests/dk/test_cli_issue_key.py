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
