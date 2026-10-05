"""Canonical roots for operator scripts under digiquant/scripts/research.

``Path(__file__).parent.parent`` from a script in this directory is
``digiquant/scripts``. The research package, its templates, and scratch data
are not there.
"""

from __future__ import annotations

from pathlib import Path

_LIB = Path(__file__).resolve().parent
SCRIPT_DIR = _LIB.parent
# parents of lib/: research, scripts, digiquant, repo root. ``parents`` also
# includes ``/``, so the repo root is parents[3], not parents[4].
DIGIQUANT_ROOT = _LIB.parents[2]
REPO_ROOT = _LIB.parents[3]
RESEARCH_PKG = DIGIQUANT_ROOT / "src" / "digiquant" / "research"
PORTFOLIO_PKG = DIGIQUANT_ROOT / "src" / "digiquant" / "portfolio"
RESEARCH_CONFIG = RESEARCH_PKG / "config"
RESEARCH_TEMPLATES = RESEARCH_PKG / "templates"
RESEARCH_SCHEMAS = RESEARCH_TEMPLATES / "schemas"
PORTFOLIO_SCHEMAS = PORTFOLIO_PKG / "templates" / "schemas"
RUNBOOK = RESEARCH_PKG / "docs" / "RUNBOOK.md"
DIGEST_SNAPSHOT_SCHEMA = RESEARCH_TEMPLATES / "digest-snapshot-schema.json"
DELTA_REQUEST_SCHEMA = RESEARCH_TEMPLATES / "delta-request-schema.json"
SNAPSHOT_SCHEMA = RESEARCH_TEMPLATES / "snapshot-schema.json"
AGENT_CACHE_ROOT = DIGIQUANT_ROOT / "data" / "agent-cache"
SCRATCH_DATA = DIGIQUANT_ROOT / "data"
DASHBOARD_DATA_JSON = REPO_ROOT / "apps" / "dashboard" / "public" / "dashboard-data.json"


def schema_file(name: str) -> Path:
    """Resolve a schema that lives in the research or portfolio template tree."""
    for directory in (RESEARCH_SCHEMAS, PORTFOLIO_SCHEMAS):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return RESEARCH_SCHEMAS / name


def research_script(name: str) -> Path:
    return SCRIPT_DIR / name
