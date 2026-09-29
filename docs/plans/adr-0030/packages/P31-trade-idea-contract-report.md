# P3.1 — Classify trade-idea timeframe and levels

**Lane:** OpenCode free implement.

**Parent:** #4762.

## Goal

`classify_fx_trade_idea_row` reports whether a hub idea row has a consensus timeframe, what display string was ignored, whether direction is `long` or `short`, and the levels status already stored on the row. `executable` is always `False`. The function does not repair levels and does not drop the idea.

## Non-goals

- Do not recompute `complete` / `partial` / `incomplete` from entry and stop values. Copy `trade_levels.status` when the object validates. If it does not validate, report `incomplete`.
- Do not call `trade_idea_snapshot_from_fx_row` (that function raises on a free-string timeframe; this one classifies instead).
- Do not change the book.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/trade_idea_report.py`
- Create: `tests/dq/stages/test_trade_idea_report.py`

## Interfaces

```python
class TradeIdeaContractReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consensus_timeframe: ConsensusTimeframe | None
    display_timeframe: str | None
    levels_status: Literal["complete", "partial", "incomplete", "absent"]
    direction_ok: bool
    executable: Literal[False] = False

def classify_fx_trade_idea_row(row: FxTradeIdeaInput) -> TradeIdeaContractReport: ...
```

`FxTradeIdeaInput` comes from `digiquant.stages.adapters.fx_trade_idea` (P0.4).

Behavior:

- `split_timeframe(row.timeframe)` fills `consensus_timeframe` and `display_timeframe`.
- `direction_ok` is `row.direction in ("long", "short")`.
- `trade_levels is None` → `levels_status="absent"`.
- Else `TradeIdeaLevels.model_validate`. On success, `levels_status` is `parsed.status.value`. On `ValidationError`, `levels_status="incomplete"`.
- `executable` is the literal `False`. There is no parameter to flip it.

## Steps

### 1. Implement `trade_idea_report.py` as specified. Catch only `ValidationError` from the levels model.

### 2. Tests

Use `FxTradeIdeaInput` with `run_date=date(2026, 9, 29)`, `rank=1`, `pair="USD/JPY"`, `title="t"`, `thesis="th"`, `catalyst="c"`.

1. `direction="long"`, `timeframe="medium"`, `trade_levels=None` → consensus medium, display None, direction_ok True, levels `absent`, executable False.
2. `timeframe="1-3M"`, `direction="short"` → consensus None, display `"1-3M"`, direction_ok True. This must not raise.
3. `direction="bullish"`, `timeframe="long"` → `direction_ok` False. Must not raise.
4. `trade_levels` with `status="partial"` and other required keys omitted where the model allows nulls → `levels_status="partial"`. A minimal valid object is `{"status": "partial"}` because every other field has a default. Assert that.
5. `trade_levels={"status": "nope"}` → `levels_status="incomplete"`, no raise.
6. Report rejects `executable=True` if someone constructs `TradeIdeaContractReport` with that value (`ValidationError`).
7. AST scan of `trade_idea_report.py`: no import of `portfolio_ledger`, `execution`, or `brokers`.

`pytestmark = pytest.mark.unit`.

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_trade_idea_report.py -q
ruff check digiquant/src/digiquant/stages/adapters/trade_idea_report.py tests/dq/stages/test_trade_idea_report.py
ruff format --check digiquant/src/digiquant/stages/adapters/trade_idea_report.py tests/dq/stages/test_trade_idea_report.py
git add digiquant/src/digiquant/stages/adapters/trade_idea_report.py tests/dq/stages/test_trade_idea_report.py
git commit -m "feat(digiquant): classify trade idea timeframe and levels"
```

## Acceptance checklist

- [ ] Free-string timeframe does not raise and does not become `medium`.
- [ ] `executable` cannot be `True`.
- [ ] Invalid brackets are classified `incomplete`, not rewritten.
- [ ] No order type is imported.

## Dependencies

- Blocked by: P0.4.
- Unblocks: P4.1, P3.2.

## Out of scope / do not touch

- The level guard in twelve-x (side, minimum R:R, band repair). Do not reimplement it.
- Execution, brokers, dashboard UI, SQL.
