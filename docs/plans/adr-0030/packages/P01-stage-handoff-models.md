# P0.1 — Stage handoff models

**Lane:** OpenCode free implement. Needs stronger review on `refuse_order_intent` (confirm it cannot build an `OrderIntent`).

**Parent:** #4762. Spec: this file. Plan: `docs/plans/adr-0030/README.md`.

## Goal

`digiquant.stages` exports `ResearchDigest`, `TradeIdeaSnapshot`, `ConsensusTimeframe`, and `refuse_order_intent`. A unit test proves the refuse function raises and that the package source does not import the execution router, brokers, or `OrderIntent`.

## Non-goals

- No FX row adapter (P0.3, P0.4).
- No research-board model (P2.1).
- No change to `DigestPayload`, `PortfolioState`, portfolio CLI, or execution policy.
- No Supabase, no graph invoke, no cron edit.

## Files

- Create: `digiquant/src/digiquant/stages/__init__.py`
- Create: `digiquant/src/digiquant/stages/contracts.py`
- Create: `digiquant/src/digiquant/stages/timeframe.py`
- Create: `digiquant/src/digiquant/stages/adapters/__init__.py` (docstring only, so later packages add modules beside it)
- Create: `tests/dq/stages/test_contracts.py`
- Create: `tests/dq/stages/test_timeframe.py`
- Modify: `digiquant/ARCHITECTURE.md` — insert the section in step 6 immediately before the heading `## execution contracts`

Do not create `tests/dq/stages/__init__.py`.

## Interfaces this package produces

Later packages import these names. Do not rename them.

```python
class ConsensusTimeframe(StrEnum):
    MEDIUM = "medium"
    LONG = "long"

class TimeframeContractError(ValueError): ...

def split_timeframe(raw: str | None) -> tuple[ConsensusTimeframe | None, str | None]: ...

class ResearchDigest(BaseModel):
    schema_version: Literal[1]
    run_date: date
    body: str
    regime_label: str
    source: Literal["digiquant.research", "twelve-x.research"]
    composition_id: Literal["digiquant-baseline", "twelve-x"]

def research_digest_from_digest_payload(
    payload: DigestPayload,
    *,
    composition_id: Literal["digiquant-baseline"] = "digiquant-baseline",
) -> ResearchDigest: ...

class TradeIdeaLevel(BaseModel): ...
class TradeIdeaLevels(BaseModel): ...
class TradeIdeaSnapshot(BaseModel): ...

class ExecutionOptInRequired(Exception): ...

def refuse_order_intent(idea: TradeIdeaSnapshot) -> None: ...
```

`research_digest_from_digest_payload` always sets `source="digiquant.research"`. The twelve-x source value is reserved for P0.3.

## Steps

### 1. Write `digiquant/src/digiquant/stages/timeframe.py`

```python
"""Consensus timeframe contract for ADR-0030 stage handoffs.

``medium`` and ``long`` are the contract. Every other string is display-only.
"""

from __future__ import annotations

from enum import StrEnum


class ConsensusTimeframe(StrEnum):
    MEDIUM = "medium"
    LONG = "long"


class TimeframeContractError(ValueError):
    """Raised when a caller required a consensus timeframe and none was present."""


def split_timeframe(raw: str | None) -> tuple[ConsensusTimeframe | None, str | None]:
    """Split a hub timeframe string into contract vs display.

    ``medium`` and ``long`` are case-sensitive. ``Medium``, ``1-3M``, blank,
    and ``None`` are not consensus values. A non-empty non-contract string is
    returned as display text and does not raise.
    """
    if raw is None:
        return None, None
    text = raw.strip()
    if text == "":
        return None, None
    if text == ConsensusTimeframe.MEDIUM.value:
        return ConsensusTimeframe.MEDIUM, None
    if text == ConsensusTimeframe.LONG.value:
        return ConsensusTimeframe.LONG, None
    return None, text
```

### 2. Write `digiquant/src/digiquant/stages/contracts.py`

```python
"""Stage handoff models for ADR-0030.

Research output is ``ResearchDigest``. Trade-generation output is
``TradeIdeaSnapshot``. Neither type is an ``OrderIntent``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from digiquant.research.segments import digest_briefing_for_portfolio
from digiquant.research.snapshot import DigestPayload
from digiquant.stages.timeframe import ConsensusTimeframe
from pydantic import BaseModel, ConfigDict, Field


class StageId(StrEnum):
    RESEARCH = "research"
    INVESTMENT = "investment"
    EXECUTION = "execution"


class Stage2Kind(StrEnum):
    PORTFOLIO = "portfolio"
    TRADE_GENERATION = "trade_generation"


class ResearchDigest(BaseModel):
    """Stage-1 handoff. Briefing fields only, plus producer identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_date: date
    body: str = Field(min_length=1)
    regime_label: str = ""
    source: Literal["digiquant.research", "twelve-x.research"]
    composition_id: Literal["digiquant-baseline", "twelve-x"]


def research_digest_from_digest_payload(
    payload: DigestPayload,
    *,
    composition_id: Literal["digiquant-baseline"] = "digiquant-baseline",
) -> ResearchDigest:
    """Copy the briefing thesis/market already read. Drop every other digest field."""
    brief = digest_briefing_for_portfolio(payload.model_dump(mode="json"))
    if "date" not in brief or "body" not in brief:
        raise ValueError("DigestPayload briefing is missing date or body")
    return ResearchDigest(
        run_date=date.fromisoformat(str(brief["date"])[:10]),
        body=brief["body"],
        regime_label=brief.get("regime_label", ""),
        source="digiquant.research",
        composition_id=composition_id,
    )


class LevelProvenance(StrEnum):
    BROKER_QUOTED = "broker_quoted"
    PMT_BANK_TRADE = "pmt_bank_trade"
    PMT_SEASONALITY_TARGET = "pmt_seasonality_target"
    PMT_POSITION_CLUSTER = "pmt_position_cluster"
    PMT_RETAIL_BOOK = "pmt_retail_book"
    COMPUTED = "computed"
    TECHNICAL = "technical"
    LLM = "llm"


class LevelStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INCOMPLETE = "incomplete"


class TradeIdeaLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    provenance: LevelProvenance
    source_ref: str


class TradeIdeaLevels(BaseModel):
    """Mirrors ``FxTradeLevels`` in ``apps/dashboard/lib/twelve-x/types.ts``."""

    model_config = ConfigDict(extra="forbid")

    entry_low: TradeIdeaLevel | None = None
    entry_high: TradeIdeaLevel | None = None
    stop: TradeIdeaLevel | None = None
    targets: list[TradeIdeaLevel] = Field(default_factory=list)
    risk_reward: float | None = None
    status: LevelStatus


class TradeIdeaSnapshot(BaseModel):
    """Stage-2 trade-generation row. Not an order."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_date: date
    rank: int = Field(ge=1)
    pair: str = Field(min_length=1)
    direction: Literal["long", "short"]
    title: str
    thesis: str
    catalyst: str
    consensus_timeframe: ConsensusTimeframe
    display_timeframe: str | None = None
    levels: TradeIdeaLevels | None = None
    idea_id: str | None = None
    as_of: datetime | None = None


class ExecutionOptInRequired(Exception):
    """Trade ideas are not submittable. A later human-gated issue would opt in."""


def refuse_order_intent(idea: TradeIdeaSnapshot) -> None:
    """Refuse to turn a trade idea into an OrderIntent.

    There is no mapping. Calling this is the execution boundary. It does not
    write a row and it does not read the execution router.
    """
    raise ExecutionOptInRequired(
        "Trade ideas do not become OrderIntent rows. twelve-x does not execute. "
        "Only digiquant.execution may submit, and only after a separate human-gated "
        f"issue. idea_id={idea.idea_id!r} pair={idea.pair!r} rank={idea.rank}"
    )
```

### 3. Write `digiquant/src/digiquant/stages/__init__.py`

Re-export every public class and function from `contracts` and `timeframe`. Do not import `digiquant.stages.adapters` here.

```python
"""Swappable digiquant stage handoffs (ADR-0030).

Adapters live in ``digiquant.stages.adapters`` and are imported from there.
"""

from digiquant.stages.contracts import (
    ExecutionOptInRequired,
    LevelProvenance,
    LevelStatus,
    ResearchDigest,
    Stage2Kind,
    StageId,
    TradeIdeaLevel,
    TradeIdeaLevels,
    TradeIdeaSnapshot,
    refuse_order_intent,
    research_digest_from_digest_payload,
)
from digiquant.stages.timeframe import (
    ConsensusTimeframe,
    TimeframeContractError,
    split_timeframe,
)

__all__ = [
    "ConsensusTimeframe",
    "ExecutionOptInRequired",
    "LevelProvenance",
    "LevelStatus",
    "ResearchDigest",
    "Stage2Kind",
    "StageId",
    "TimeframeContractError",
    "TradeIdeaLevel",
    "TradeIdeaLevels",
    "TradeIdeaSnapshot",
    "refuse_order_intent",
    "research_digest_from_digest_payload",
    "split_timeframe",
]
```

### 4. Write `digiquant/src/digiquant/stages/adapters/__init__.py`

```python
"""Pure adapters between stage handoffs and reader rows.

Modules are added by later ADR-0030 packages. This file stays import-free.
"""
```

### 5. Tests

`tests/dq/stages/test_timeframe.py`:

```python
from __future__ import annotations

import pytest
from digiquant.stages import ConsensusTimeframe, split_timeframe

pytestmark = pytest.mark.unit


def test_medium_and_long_are_consensus() -> None:
    assert split_timeframe("medium") == (ConsensusTimeframe.MEDIUM, None)
    assert split_timeframe("long") == (ConsensusTimeframe.LONG, None)


def test_free_string_is_display_only() -> None:
    assert split_timeframe("1-3M") == (None, "1-3M")
    assert split_timeframe(" Medium ") == (None, "Medium")


def test_blank_is_neither() -> None:
    assert split_timeframe(None) == (None, None)
    assert split_timeframe("  ") == (None, None)
```

`tests/dq/stages/test_contracts.py` cases:

1. `research_digest_from_digest_payload` on a `DigestPayload(date=date(2026, 9, 29), body="hello", regime_label="Risk-on")` returns `run_date` 2026-09-29, `body` `"hello"`, `regime_label` `"Risk-on"`, `source` `"digiquant.research"`, `composition_id` `"digiquant-baseline"`.
2. A payload with `body=""` and no legacy sections raises `ValueError` matching `missing date or body`.
3. `ResearchDigest` rejects `composition_id="other"` (`ValidationError`).
4. `refuse_order_intent` on a minimal `TradeIdeaSnapshot` (`run_date=date(2026, 9, 29)`, `rank=1`, `pair="USD/JPY"`, `direction="long"`, `title="t"`, `thesis="th"`, `catalyst="c"`, `consensus_timeframe=ConsensusTimeframe.MEDIUM`) raises `ExecutionOptInRequired` matching `does not execute`.
5. AST scan of every `*.py` file under `digiquant/src/digiquant/stages/` : no `Import` or `ImportFrom` whose module contains `digiquant.execution`, `digiquant.brokers`, or `digiquant.portfolio.models.portfolio_ledger`. String text in `refuse_order_intent`'s message may contain the word `OrderIntent`.
6. `TradeIdeaLevels` rejects `provenance="guessed"` on a level (`ValidationError`).

Use `pytestmark = pytest.mark.unit`. Build the AST scan with `ast.walk` over `Path` files. Do not shell out.

### 6. ARCHITECTURE.md

Immediately before the heading `## execution contracts`, insert:

```markdown
## Stage contracts (ADR-0030)

Swappable handoffs live in `digiquant.stages`. `ResearchDigest` is the stage-1
briefing (`date`, `body`, `regime_label`) plus `source` and `composition_id`.
`TradeIdeaSnapshot` is the stage-2 trade-idea row. `refuse_order_intent` raises
`ExecutionOptInRequired` and does not build an `OrderIntent`.

Consensus timeframes are `medium` and `long`. Other strings are display-only
(`split_timeframe`). twelve-x trade generation stays in the twelve-x repo.
twelve-x does not execute. `PortfolioState` remains an alias of `ResearchState`.
The portfolio `--from-digest` CLI still loads a full `ResearchState`.

Plan: `docs/plans/adr-0030/README.md`. Decision: ADR-0030.
```

### 7. Run

```bash
pytest -m unit tests/dq/stages/test_contracts.py tests/dq/stages/test_timeframe.py -q
ruff check digiquant/src/digiquant/stages tests/dq/stages
ruff format --check digiquant/src/digiquant/stages tests/dq/stages
```

Expected: pytest pass, ruff clean.

### 8. Commit

```bash
git add digiquant/src/digiquant/stages tests/dq/stages digiquant/ARCHITECTURE.md
git commit -m "feat(digiquant): add ADR-0030 stage handoff models"
```

## Acceptance checklist

- [ ] Public names match the interface block above.
- [ ] `refuse_order_intent` raises and the stages tree does not import execution, brokers, or `OrderIntent`'s module.
- [ ] `medium` / `long` vs `1-3M` behavior matches the tests.
- [ ] ARCHITECTURE section sits immediately before `## execution contracts`.
- [ ] No file under `digiquant/brokers/` or `digiquant/src/digiquant/execution/` changed.
- [ ] PR body contains `Refs #4762` and the child issue number. It does not contain `Fixes #4762`.

## Dependencies

- Blocked by: none.
- Unblocks: P0.3, P0.4, P1.2, P2.1.

## Out of scope / do not touch

- `digiquant/brokers/**`
- `digiquant/src/digiquant/execution/**`
- `DIGIQUANT_EXECUTION_ROUTING`
- `digiquant/src/digiquant/portfolio/graph.py` `_load_state`
- `digiquant/src/digiquant/portfolio/state.py` alias
- `apps/dashboard/**`
- `apps/digithings-cron/**`
- `.github/workflows/**`
- twelve-x repo
- Any SQL migration
