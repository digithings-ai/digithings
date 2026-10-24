# P2.1 — twelve-x research board validator

**Lane:** OpenCode free implement.

**Parent:** #4762.

## Goal

`parse_research_board` validates one run's stage-1 hub rows into `TwelveXResearchBoard`: the daily digest, desk briefs, relevance ledger, events, and consensus rows whose timeframe is `medium` or `long`. It does not score relevance and it does not rank ideas.

## Non-goals

- Do not compute consensus, confluence, or `w_time * w_event * w_review`.
- Do not drop or rewrite ideas.
- Do not coerce a consensus timeframe other than `medium` or `long`.
- Do not fetch from Supabase. The caller passes a dict.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/research_board.py`
- Create: `tests/dq/stages/test_research_board.py`

Reader shapes copied from `apps/dashboard/lib/twelve-x/types.ts`. Do not edit that file.

## Interfaces

```python
class FxBriefCurrencyViewInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    currency: str
    direction: str
    conviction: str
    signal: str | None = None
    rationale: str | None = None
    key_facts: list[str] = Field(default_factory=list)

class FxBriefInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_date: date
    source_file: str
    broker_name: str | None = None
    analyst_names: list[str] | None = None
    central_thesis: str | None = None
    brief_markdown: str | None = None
    trader_relevance: str | None = None
    currency_views: list[FxBriefCurrencyViewInput] = Field(default_factory=list)

class FxLedgerInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_date: date
    source_file: str
    view_index: int
    broker_name: str | None = None
    currency: str
    direction: str
    conviction: str | None = None
    relevance: float
    classification: str
    reason: str | None = None

class FxEventInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_date: date
    event_key: str
    event_name: str
    event_date: date | None = None
    category: str = ""
    mentions: int = 0

class FxConsensusInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_date: date
    currency: str
    timeframe: ConsensusTimeframe
    weighted: bool
    score: float

class TwelveXResearchBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    run_date: date
    digest: FxDailyDigestInput
    briefs: list[FxBriefInput]
    ledger: list[FxLedgerInput]
    events: list[FxEventInput]
    consensus: list[FxConsensusInput]

def parse_research_board(payload: Mapping[str, Any]) -> TwelveXResearchBoard: ...
```

`FxDailyDigestInput` is imported from `digiquant.stages.adapters.fx_digest` (P0.3). If P0.3 has not merged, do not copy that class. Wait for P0.3. This package is blocked by P0.1 in the wave graph and by P0.3 for the digest model. The master plan lists P2.1 blocked by P0.1 only, so **define the board's digest field as `ResearchDigest` is wrong**. Use `FxDailyDigestInput`.

Conflict resolution for the implementer: P2.1's code imports `FxDailyDigestInput` from P0.3. Treat P0.3 as a blocker even though the wave diagram drew P2.1 directly off P0.1. If P0.3 is not merged, stop and say so. Do not duplicate `FxDailyDigestInput`.

`parse_research_board` expects this dict shape:

```python
{
    "run_date": "2026-09-29",
    "digest": {"run_date": "2026-09-29", "summary": "...", "key_themes": [], "doc_count": 0, "broker_count": 0},
    "briefs": [],
    "ledger": [],
    "events": [],
    "consensus": [],
}
```

Rules:

- `digest.run_date` must equal top-level `run_date`. Else `ValueError` matching `run_date`.
- Every brief, ledger row, event, and consensus row must have the same `run_date`. Else `ValueError` matching `run_date`.
- Consensus `timeframe` must already be `medium` or `long`. `"1-3M"` raises `ValidationError` from Pydantic. Do not catch it and do not coerce.
- Empty `briefs`, `ledger`, `events`, and `consensus` are valid. Missing `digest` is not.
- `targets` inside a currency view stay in `extra` (`extra="allow"` on the view). Do not read them.

## Steps

### 1. Implement `research_board.py` with the models above and:

```python
def parse_research_board(payload: Mapping[str, Any]) -> TwelveXResearchBoard:
    board = TwelveXResearchBoard.model_validate(payload)
    _same_run_date(board)
    return board


def _same_run_date(board: TwelveXResearchBoard) -> None:
    rows: list[date] = [board.digest.run_date]
    rows.extend(item.run_date for item in board.briefs)
    rows.extend(item.run_date for item in board.ledger)
    rows.extend(item.run_date for item in board.events)
    rows.extend(item.run_date for item in board.consensus)
    for row_date in rows:
        if row_date != board.run_date:
            raise ValueError(
                f"research board run_date {board.run_date.isoformat()} "
                f"does not match row run_date {row_date.isoformat()}"
            )
```

### 2. Tests

1. Minimal payload (digest summary `"Quiet."`, empty lists) parses. `board.digest.summary == "Quiet."`.
2. Consensus row `timeframe="medium"`, `currency="USD"`, `weighted=True`, `score=0.4` parses as `ConsensusTimeframe.MEDIUM`.
3. Consensus `timeframe="1-3M"` raises `ValidationError`.
4. A brief with `run_date` one day later raises `ValueError` matching `run_date`.
5. A currency view with extra `targets=["1.10"]` parses, and `view.targets` is accessible via `model_extra` or attribute if extra allow stores it. Assert `"targets" in (view.model_extra or {})` when passed as a dict through `model_validate`. Do not add a `targets` field.
6. AST scan: `research_board.py` does not import `digiquant.portfolio`, `digiquant.execution`, or `digiquant.brokers`.

`pytestmark = pytest.mark.unit`.

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_research_board.py -q
ruff check digiquant/src/digiquant/stages/adapters/research_board.py tests/dq/stages/test_research_board.py
ruff format --check digiquant/src/digiquant/stages/adapters/research_board.py tests/dq/stages/test_research_board.py
git add digiquant/src/digiquant/stages/adapters/research_board.py tests/dq/stages/test_research_board.py
git commit -m "feat(digiquant): validate twelve-x research board rows"
```

## Acceptance checklist

- [ ] Consensus rejects free-string timeframes.
- [ ] Digest is required; child lists may be empty.
- [ ] Mixed `run_date` values fail.
- [ ] No scoring function was added.
- [ ] `types.ts` is unchanged.

## Dependencies

- Blocked by: P0.1 and P0.3 (`FxDailyDigestInput`). The master wave draws P2.1 off P0.1; wait for P0.3 as well so the digest model is not copied.
- Unblocks: P4.1, P4.2, P2.2.

## Out of scope / do not touch

- Relevance formula, consensus math, confluence `build_confluence`.
- Scrapers, `digifetch`, Prime Market credentials.
- Execution, brokers, SQL, twelve-x repo.
