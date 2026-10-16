# P4.1 — ResearchDigest wrapped as trade-generation input

**Lane:** OpenCode free implement.

**Parent:** #4762. Last among the digiquant-side feature seams. Do not start until P2.1 and P3.1 have merged.

## Goal

`trade_generation_input_from_research_digest` wraps a `ResearchDigest` in `TradeGenerationInput`. Pair allow, pair deny, and risk style are fixed `None`. `watchlist_steers_writer` is fixed `False`. The function returns that object and nothing else. It does not synthesize ideas.

## Non-goals

- Do not rank, call an LLM, or read `fx_trade_ideas_snapshot`.
- Do not accept a watchlist argument.
- Do not call twelve-x.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/trade_generation_input.py`
- Create: `tests/dq/stages/test_trade_generation_input.py`

## Interface

```python
class TradeGenerationInput(BaseModel):
    """Stage-2 input when the research module is digiquant and the book is trade ideas.

    The unwired hub directives stay unwired: allow, deny, risk style, watchlist.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    digest: ResearchDigest
    pair_allow: None = None
    pair_deny: None = None
    risk_style: None = None
    watchlist_steers_writer: Literal[False] = False

def trade_generation_input_from_research_digest(digest: ResearchDigest) -> TradeGenerationInput: ...
```

The function body is `return TradeGenerationInput(digest=digest)`.

## Steps

### 1. Implement the module exactly as the interface. No extra parameters.

### 2. Tests

1. A `ResearchDigest` with `source="digiquant.research"`, `composition_id="digiquant-baseline"`, `run_date=date(2026, 9, 29)`, `body="House digest."` round-trips onto `result.digest`.
2. `result.pair_allow is None`, `result.pair_deny is None`, `result.risk_style is None`, `result.watchlist_steers_writer is False`.
3. `TradeGenerationInput(digest=digest, pair_allow=["EUR/USD"])` raises `ValidationError`.
4. `TradeGenerationInput(digest=digest, watchlist_steers_writer=True)` raises `ValidationError`.
5. `inspect.signature(trade_generation_input_from_research_digest).parameters` has exactly one parameter, `digest`.
6. AST scan: file does not import portfolio graph, execution, brokers, or `fx_trade_idea`.

Also import `classify_fx_trade_idea_row` in the test module and call it on a tiny `FxTradeIdeaInput` so this package's test fails to collect if P3.1 is missing. That is the wave gate: one assertion `report.executable is False`. Do not use that report to build the input.

`pytestmark = pytest.mark.unit`.

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_trade_generation_input.py -q
ruff check digiquant/src/digiquant/stages/adapters/trade_generation_input.py tests/dq/stages/test_trade_generation_input.py
ruff format --check digiquant/src/digiquant/stages/adapters/trade_generation_input.py tests/dq/stages/test_trade_generation_input.py
git add digiquant/src/digiquant/stages/adapters/trade_generation_input.py tests/dq/stages/test_trade_generation_input.py
git commit -m "feat(digiquant): wrap ResearchDigest as trade generation input"
```

## Acceptance checklist

- [ ] No ideas are emitted. Return type is `TradeGenerationInput`, not `TradeIdeaSnapshot`.
- [ ] Allow, deny, risk style, and watchlist cannot be turned on through the model.
- [ ] Signature has no watchlist parameter.
- [ ] No network, no graph.

## Dependencies

- Blocked by: P2.1 and P3.1 (wave order). The type itself only needs `ResearchDigest` from P0.1. Still wait.
- Unblocks: nothing else in this epic.

## Out of scope / do not touch

- twelve-x strategist passes, ranking, levels.
- Execution and brokers.
- Dashboard watchlist code (`useWatchlist.ts`). Leave it unwired.
