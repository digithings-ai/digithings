"""Export profile JSON schemas to ``digiquant/docs/schemas/``.

Regenerate after any change to a model in ``digiquant.profiles`` and commit
the result alongside the model change. Run from the repo root::

    python3 scripts/export_profile_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Make the digiquant package importable when invoked outside an editable install.
sys.path.insert(0, str(REPO_ROOT / "digiquant" / "src"))

from digiquant.profiles.asset_preferences import AssetPreferences  # noqa: E402
from digiquant.profiles.investment_profile import InvestmentProfile  # noqa: E402

_SCHEMAS = (
    (InvestmentProfile, "investment_profile.v1.json"),
    (AssetPreferences, "asset_preferences.v1.json"),
)


def main() -> int:
    out_dir = REPO_ROOT / "digiquant" / "docs" / "schemas"
    out_dir.mkdir(parents=True, exist_ok=True)
    for model, filename in _SCHEMAS:
        out = out_dir / filename
        schema = model.model_json_schema()
        out.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
