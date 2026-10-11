"""Keep the digillm suite out of the production egress ledger.

``digillm.egress_record`` appends one JSONL line per outbound call to
``digiquant/results/egress/records.jsonl`` *by default*, with nobody registered.
That default is the deliverable — "the audit trail exists" is the point — but it
also means one test run pushes mock rows into the very file the ledger is read
from, with ``destination`` values like ``<MagicMock name='mock.base_url' ...>``.
Those rows are indistinguishable from production egress, and they land in a
directory that is gitignored yet bind-mounted into containers and swept by
routine artifact cleaning.

So the suite points the sink at pytest's ``tmp_path`` instead. Nothing is
weakened: ``test_egress_record.py`` still proves the default sink is a real local
sink rather than a no-op, because it sets ``DIGILLM_EGRESS_LOG_PATH`` itself and
its assertion is about the *unregistered* default. Both fixtures compute the same
``tmp_path``-derived path, so their relative order cannot change the result.

The import below is deliberately unguarded. This file ships alongside
``egress_record`` itself, and a silent ``try: import ... except ImportError:
pass`` would put the pollution straight back while reporting green.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from digillm import egress_record


@pytest.fixture(autouse=True)
def _isolate_egress_sink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Redirect the JSONL sink into ``tmp_path`` and clear the observer.

    Autouse for the whole directory, so no module opts out by forgetting to
    isolate itself: the leak is the default, and a default that has to be opted
    out of per module is not a default. ``monkeypatch`` restores the variable
    afterwards, and the teardown drops an observer a test registered, so neither
    the path nor the callback escapes into the next test.
    """
    sink = tmp_path / "egress" / "records.jsonl"
    monkeypatch.setenv(egress_record.EGRESS_LOG_PATH_ENV, str(sink))
    egress_record.set_egress_observer(None)
    yield
    egress_record.set_egress_observer(None)
