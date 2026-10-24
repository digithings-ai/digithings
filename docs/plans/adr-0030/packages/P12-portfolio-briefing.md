# P1.2 — Portfolio briefing dict from ResearchDigest

**Lane:** OpenCode free implement.

**Parent:** #4762.

## Goal

`portfolio_briefing_from_research_digest` returns the same three keys thesis and market already read (`date`, `body`, `regime_label`) from a `ResearchDigest`. It does not load `ResearchState`, does not change `--from-digest`, and does not invoke the portfolio graph.

## Non-goals

- Do not change `PortfolioState = ResearchState`.
- Do not change `_load_state` or add a CLI flag.
- Do not call `build_portfolio_graph` or `run_research_then_portfolio`.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/portfolio_briefing.py`
- Create: `tests/dq/stages/test_portfolio_briefing.py`

## Interface

```python
def portfolio_briefing_from_research_digest(digest: ResearchDigest) -> dict[str, str]:
    """Keys match ``digest_briefing_for_portfolio``: date, body, and regime_label when set."""
```

Rules:

- `date` is `digest.run_date.isoformat()`.
- `body` is `digest.body` unchanged.
- Include `regime_label` only when `digest.regime_label.strip()` is non-empty. This matches `digest_briefing_for_portfolio`, which omits a blank regime.
- Return type is `dict[str, str]`. No other keys.

## Steps

### 1. Implement

```python
"""Briefing dict stage 2 already consumes, built from a ResearchDigest."""

from __future__ import annotations

from digiquant.stages.contracts import ResearchDigest


def portfolio_briefing_from_research_digest(digest: ResearchDigest) -> dict[str, str]:
    out: dict[str, str] = {
        "date": digest.run_date.isoformat(),
        "body": digest.body,
    }
    regime = digest.regime_label.strip()
    if regime:
        out["regime_label"] = regime
    return out
```

### 2. Tests

1. Build a `DigestPayload` with `date=date(2026, 9, 29)`, `body="Desk read."`, `regime_label="Risk-on"`. Run `research_digest_from_digest_payload`. The briefing helper's result equals `digest_briefing_for_portfolio(payload.model_dump(mode="json"))`.
2. A `ResearchDigest` with `regime_label=""` omits `regime_label` from the dict. Keys are exactly `date` and `body`.
3. AST scan of `portfolio_briefing.py`: no import of `digiquant.portfolio`, `digiquant.execution`, or `digiquant.brokers`.

`pytestmark = pytest.mark.unit`.

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_portfolio_briefing.py -q
ruff check digiquant/src/digiquant/stages/adapters/portfolio_briefing.py tests/dq/stages/test_portfolio_briefing.py
ruff format --check digiquant/src/digiquant/stages/adapters/portfolio_briefing.py tests/dq/stages/test_portfolio_briefing.py
git add digiquant/src/digiquant/stages/adapters/portfolio_briefing.py tests/dq/stages/test_portfolio_briefing.py
git commit -m "feat(digiquant): build portfolio briefing from ResearchDigest"
```

## Acceptance checklist

- [ ] Dict keys are only `date`, `body`, and optionally `regime_label`.
- [ ] Parity with `digest_briefing_for_portfolio` holds for the case in test 1.
- [ ] `portfolio/graph.py` and `portfolio/state.py` have an empty diff.
- [ ] No graph invoke.

## Dependencies

- Blocked by: P0.1.
- Unblocks: P4.2.

## Out of scope / do not touch

- Portfolio phases, commit, ledger writers.
- Execution and brokers.
- twelve-x tables.
