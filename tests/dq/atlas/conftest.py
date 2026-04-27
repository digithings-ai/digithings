"""Atlas test collection gate.

The Atlas sub-package imports `digigraph` (workspace-local, not on PyPI).
The standard `digiquant-test` CI job only installs `digiquant[dev]`, which
does NOT pull `digigraph` — so collecting the Atlas tests there would fail
with ImportError. The full Atlas test set runs in `atlas-graph-ci.yml`
where install-workspace.sh has put digigraph on sys.path first.
"""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec("digigraph") is None:
    collect_ignore_glob = ["test_*.py", "phases/test_*.py"]
