"""Atlas test collection gate.

The Atlas sub-package imports `digigraph.graph.pipeline_builder`, which in
turn pulls `openai` (a digigraph dependency). The standard `digiquant-test`
CI job installs only `digiquant[dev]`, so digigraph's runtime deps are
absent — collecting the Atlas tests there would error out.

The repo-root pytest.ini puts all `*/src` directories on pythonpath, which
means `find_spec("digigraph")` succeeds even when digigraph is not
pip-installed. So we must actually attempt the import to know whether the
chain is wired up.

The full Atlas test set runs in `atlas-graph-ci.yml` where
install-workspace.sh has installed digigraph + its deps first.
"""

from __future__ import annotations


def _digigraph_importable() -> bool:
    try:
        import digigraph.graph.pipeline_builder  # noqa: F401
    except ImportError:
        return False
    return True


if not _digigraph_importable():
    collect_ignore_glob = ["test_*.py", "phases/test_*.py"]
