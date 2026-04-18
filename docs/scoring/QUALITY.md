# Quality Rubric (10-point)

**Target: ≥ 8/10 to merge. < 7 blocks merge.**

Score one point per criterion you fully satisfy.

---

## Criteria

| # | Criterion | Points | How to Check | How to Fix |
|---|-----------|--------|-------------|-----------|
| 1 | **Pydantic v2 everywhere** — All structured data uses Pydantic v2 models (`model_validator`, `field_validator`, not v1 `validator`); no plain `dict` as a return type from public functions | 1 | Search diff for `@validator`, `class Config:`, `dict` return annotations on public APIs | Migrate to `@model_validator`/`@field_validator`; add typed return models |
| 2 | **Polars only — no pandas** — No `import pandas`, no `pd.`, no `.to_pandas()` except in explicit export adapters (broker/TradingView) | 1 | `grep -n "import pandas\|pd\." diff` | Replace with Polars equivalent; `pl.DataFrame`, `pl.LazyFrame` |
| 3 | **Strict typing — no untyped Any** — All function signatures have type annotations; `Any` is only used with an inline `# noqa: ANN401` comment explaining why | 1 | Run `ruff check --select ANN` on changed files | Add type annotations; replace `Any` with a concrete type or `TypeVar` |
| 4 | **Ruff clean** — `ruff check .` and `ruff format --check .` pass with zero errors on changed files (line-length 100, target py312) | 1 | Run `ruff check . && ruff format --check .` | Run `ruff format .` then fix lint errors |
| 5 | **Tests added or updated** — Every new public function, class, or HTTP route has at least one unit test; changed behavior has updated assertions | 1 | Check that there is a corresponding `tests/` change for each new or modified function | Add `pytest -m unit` tests under the component's `tests/` directory |
| 6 | **No orphaned code** — Removed functions are also removed from `__init__.py` exports and from any import sites; no dead branches | 1 | Search for removed symbol names in `__init__.py` and other files | Clean up exports and callers; confirm with `grep` |
| 7 | **Files stay focused** — No new file is > 400 lines; no function is > 60 lines without a clear justification; helpers are co-located with their only consumer | 1 | `wc -l` new files; eyeball function lengths | Extract sub-functions; split large files into logical sub-modules |
| 8 | **Errors are structured** — All new `raise` statements use the `digibase` error envelope pattern or a Pydantic model with `code` and `message`; no bare `raise Exception("string")` | 1 | Search diff for `raise Exception`, `raise ValueError` without structured detail | Use `HTTPException` with `detail={"code": ..., "message": ...}` or a Pydantic error model |
| 9 | **ARCHITECTURE.md updated** — If a new module, file, public endpoint, env var, or data model was added, the component's `ARCHITECTURE.md` reflects the change | 1 | Compare diff against component ARCHITECTURE.md; check Module Map, Public API, Configuration sections | Update the relevant section of `{component}/ARCHITECTURE.md` |
| 10 | **No backward-compat hacks** — No unused `_old_` variable prefixes, no `# TODO: remove` comments left unfixed, no aliased imports that exist only for compatibility | 1 | Search diff for `_old`, `# TODO: remove`, redundant aliases | Remove cleanly; update all call sites |

---

## Examples

### Passing (Score: 10)

```python
# Strict types, Pydantic v2, structured errors, focused function
from pydantic import BaseModel, field_validator
import polars as pl

class BacktestRequest(BaseModel):
    strategy: str
    symbols: list[str]

    @field_validator("symbols")
    @classmethod
    def symbols_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("symbols must not be empty")
        return v

def load_ohlcv(data_path: str) -> pl.LazyFrame:
    return pl.scan_csv(data_path)
```

### Failing (Score: 6 — criteria 1, 2, 3 fail)

```python
import pandas as pd
from typing import Any

def load_data(path) -> Any:  # No annotation, returns Any
    return pd.read_csv(path)  # pandas, no Pydantic
```

---

## Notes

- Criterion 4 (ruff) is a hard gate. CI also runs ruff; if CI fails, the PR cannot merge regardless of self-score.
- Criterion 9 is the most commonly skipped by agents. Always update ARCHITECTURE.md when adding code.
