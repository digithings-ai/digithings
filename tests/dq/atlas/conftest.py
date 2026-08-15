"""Atlas test collection gate.

The Atlas sub-package imports `digigraph.graph.pipeline_builder`, which in
turn pulls `openai` (a digigraph dependency). The standard `digiquant-test`
CI job installs only `digiquant[dev]`, so digigraph's runtime deps are
absent — collecting the Atlas tests there would error out.

The repo-root pytest.ini puts all `*/src` directories on pythonpath, which
means `find_spec("digigraph")` succeeds even when digigraph is not
pip-installed. So we must actually attempt the import to know whether the
chain is wired up.

The full Atlas test set runs in `test-atlas-graph.yml` where
install-workspace.sh has installed digigraph + its deps first.

`data/test_*.py` was dropped from the glob below (#2183): of the five files
under `tests/dq/atlas/data/`, only `test_ai_portfolios.py` and
`test_web_grounding.py` actually need digigraph, and both already guard
themselves with a module-level `pytest.importorskip("openai")` — the same
absent dependency this docstring's second paragraph names, and the actual
reason those two modules can't be collected here, not digigraph directly.
`importorskip` reports a clean SKIP rather than a collection error, so this
file-level glob was only ever needed for the *other* three files in that
directory (`test_queries.py`, `test_queries_derived.py`, `test_tools.py`),
which have no digigraph dependency at all and were being swept out with them
for no reason — verified empirically: removing this entry runs all three
files' ~29 tests clean in the digiquant-only lane, while the two
digigraph-dependent files still report as skipped, not errored.

`phases/test_*.py` is removed outright: there is no `tests/dq/atlas/phases/`
directory in this repo, so the pattern has never matched anything.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any  # score:allow untyped any — contributor payloads are free-form jsonb

import pytest


def _digigraph_importable() -> bool:
    try:
        import digigraph.graph.pipeline_builder  # noqa: F401
    except ImportError:
        return False
    return True


if not _digigraph_importable():
    collect_ignore_glob = ["test_*.py"]


@pytest.fixture
def breakdown_contributor() -> Iterator[Callable[..., None]]:
    """Register diagnostics ``breakdown`` contributors for the duration of one test.

    ``_BREAKDOWN_CONTRIBUTORS`` is process-global, so registering one in a test would leak
    into every later test in the session. Snapshot-and-restore keeps each test isolated.
    Shared here (rather than in ``test_diagnostics.py``) because every package that adds a
    breakdown key needs it — see ``diagnostics.register_breakdown_contributor`` (#1736).
    """
    from digiquant.olympus.atlas import diagnostics

    saved = list(diagnostics._BREAKDOWN_CONTRIBUTORS)

    def _register(fn: Callable[[Any], dict[str, Any]]) -> None:
        diagnostics.register_breakdown_contributor(fn)

    try:
        yield _register
    finally:
        diagnostics._BREAKDOWN_CONTRIBUTORS[:] = saved
