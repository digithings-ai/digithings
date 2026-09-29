# P0.4 — fx trade idea row → TradeIdeaSnapshot

**Lane:** OpenCode free implement. Stronger review: the adapter must not construct `OrderIntent` or call `refuse_order_intent` during a successful map (the refuse function stays a separate call).

**Parent:** #4762.

## Goal

`trade_idea_snapshot_from_fx_row` maps one `fx_trade_ideas_snapshot` reader row onto `TradeIdeaSnapshot`. Consensus timeframe is `medium` or `long` only. Any other timeframe string is `display_timeframe`. The raw `levels` jsonb array is ignored. Structured `trade_levels` map field-for-field. The function never imports `OrderIntent`.

## Non-goals

- Do not repair brackets, fill missing stops, or change rank.
- Do not coerce `bullish` into `long`.
- Do not default a missing timeframe to `medium`.
- Do not write snapshot rows.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/fx_trade_idea.py`
- Create: `tests/dq/stages/test_fx_trade_idea_adapter.py`

## Interfaces

```python
class FxTradeIdeaInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_date: date
    rank: int
    pair: str
    direction: str
    title: str
    thesis: str
    catalyst: str
    as_of: datetime | None = None
    trade_levels: dict[str, Any] | None = None
    idea_id: str | None = None
    timeframe: str | None = None

def trade_idea_snapshot_from_fx_row(
    row: FxTradeIdeaInput,
    *,
    consensus_timeframe: ConsensusTimeframe | None = None,
) -> TradeIdeaSnapshot: ...
```

Resolution of timeframe, in order:

1. `split_timeframe(row.timeframe)` yields a consensus value → use it. `display_timeframe` is `None`. Ignore the keyword argument.
2. Else if `consensus_timeframe` is passed → use it. If step 1 returned a display string, store that string on `display_timeframe`.
3. Else raise `TimeframeContractError` with the raw timeframe in the message. Do not guess.

Direction: only `long` and `short` (case-sensitive) pass. Anything else, including `bullish`, raises `ValueError` matching `direction`.

`trade_levels is None` → `levels is None`. A dict is `TradeIdeaLevels.model_validate`. Validation errors propagate. Do not catch them.

The hub field `levels` (broker jsonb array) is not a field on `FxTradeIdeaInput`. `extra="ignore"` drops it. Do not add a parser for it.

## Steps

### 1. Implement

```python
"""Map ``fx_trade_ideas_snapshot`` reader rows onto ``TradeIdeaSnapshot``."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from digiquant.stages.contracts import TradeIdeaLevels, TradeIdeaSnapshot
from digiquant.stages.timeframe import (
    ConsensusTimeframe,
    TimeframeContractError,
    split_timeframe,
)
from pydantic import BaseModel, ConfigDict, Field


class FxTradeIdeaInput(BaseModel):
    """Reader fields used by the stage-2 boundary. Extra hub keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    run_date: date
    rank: int = Field(ge=1)
    pair: str
    direction: str
    title: str
    thesis: str
    catalyst: str
    as_of: datetime | None = None
    trade_levels: dict[str, Any] | None = None
    idea_id: str | None = None
    timeframe: str | None = None


def trade_idea_snapshot_from_fx_row(
    row: FxTradeIdeaInput,
    *,
    consensus_timeframe: ConsensusTimeframe | None = None,
) -> TradeIdeaSnapshot:
    parsed, display = split_timeframe(row.timeframe)
    if parsed is None:
        if consensus_timeframe is None:
            raise TimeframeContractError(
                "trade idea timeframe is not medium or long "
                f"(raw={row.timeframe!r}); pass consensus_timeframe explicitly"
            )
        parsed = consensus_timeframe
    else:
        display = None
    if row.direction not in ("long", "short"):
        raise ValueError(
            f"trade idea direction must be long or short, got {row.direction!r}"
        )
    levels = None
    if row.trade_levels is not None:
        levels = TradeIdeaLevels.model_validate(row.trade_levels)
    return TradeIdeaSnapshot(
        run_date=row.run_date,
        rank=row.rank,
        pair=row.pair,
        direction=row.direction,  # type: ignore[arg-type]
        title=row.title,
        thesis=row.thesis,
        catalyst=row.catalyst,
        consensus_timeframe=parsed,
        display_timeframe=display,
        levels=levels,
        idea_id=row.idea_id,
        as_of=row.as_of,
    )
```

Replace the `type: ignore` by assigning `direction: Literal["long", "short"] = row.direction` after the membership check, so the snapshot call typechecks without a comment. `row.direction` is `str`; after the check, bind:

```python
direction: Literal["long", "short"] = "long" if row.direction == "long" else "short"
```

### 2. Tests

Fixture level dict (reuse in tests):

```python
_LEVEL = {"value": "150.10", "provenance": "broker_quoted", "source_ref": "desk:1"}
_LEVELS = {
    "entry_low": _LEVEL,
    "entry_high": _LEVEL,
    "stop": _LEVEL,
    "targets": [_LEVEL],
    "risk_reward": 1.8,
    "status": "complete",
}
```

Cases:

1. `timeframe="medium"` → `consensus_timeframe` medium, `display_timeframe is None`.
2. `timeframe="1-3M"` and `consensus_timeframe=ConsensusTimeframe.LONG` → consensus long, display `"1-3M"`.
3. `timeframe="1-3M"` and no keyword → `TimeframeContractError` matching `1-3M`.
4. `timeframe=None` and keyword medium → consensus medium, display `None`.
5. `direction="bullish"` → `ValueError` matching `direction`.
6. `trade_levels=_LEVELS` → `levels.status` is `LevelStatus.COMPLETE`, `levels.stop.provenance` is `LevelProvenance.BROKER_QUOTED`.
7. `trade_levels=None` → `levels is None`.
8. Input constructed with extra `levels=[{"raw": True}]` does not raise, and the snapshot has no attribute named `broker_levels`.
9. AST scan of `fx_trade_idea.py`: no import whose module contains `portfolio_ledger`, `execution`, or `brokers`.

`pytestmark = pytest.mark.unit`.

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_fx_trade_idea_adapter.py -q
ruff check digiquant/src/digiquant/stages/adapters/fx_trade_idea.py tests/dq/stages/test_fx_trade_idea_adapter.py
ruff format --check digiquant/src/digiquant/stages/adapters/fx_trade_idea.py tests/dq/stages/test_fx_trade_idea_adapter.py
git commit -am "feat(digiquant): map fx trade ideas onto TradeIdeaSnapshot"
```

Use an explicit `git add` of the two files if `-am` would pick up unrelated edits.

## Acceptance checklist

- [ ] `1-3M` never becomes `medium` by itself.
- [ ] `bullish` is rejected.
- [ ] Raw `levels` array is not interpreted.
- [ ] No `OrderIntent` import.
- [ ] Successful map does not raise `ExecutionOptInRequired`.

## Dependencies

- Blocked by: P0.1.
- Unblocks: P3.1.

## Out of scope / do not touch

- Level repair, R:R guards that rewrite stops, strategist passes.
- `OrderIntent`, router, brokers, `DIGIQUANT_EXECUTION_ROUTING`.
- twelve-x writer, SQL, dashboard components.
