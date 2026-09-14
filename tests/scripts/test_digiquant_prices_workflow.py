from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _steps() -> list[dict]:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml").read_text()
    )
    return [step for job in spec["jobs"].values() for step in job.get("steps", [])]


def test_technicals_writer_is_gone() -> None:
    assert not [s for s in _steps() if "compute-technicals" in str(s.get("run", ""))]


def test_intraday_quotes_writer_stays_for_same_day_opens() -> None:
    quote_steps = [s for s in _steps() if "fetch-quotes" in str(s.get("run", ""))]
    assert quote_steps, "fetch-quotes --supabase is the documented same-day open source (#4013 D3)"
