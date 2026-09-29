# P4.2 — Portfolio briefing from a twelve-x research board

**Lane:** OpenCode free implement.

**Parent:** #4762.

## Goal

`portfolio_briefing_from_research_board` turns a `TwelveXResearchBoard` into the briefing dict portfolio thesis/market already accept. The body comes from the fx daily digest adapter. `regime_label` is omitted, because `fx_daily_digest` has no regime field and this function must not invent one from consensus scores.

## Non-goals

- Do not invoke `build_portfolio_graph` or `run_research_then_portfolio`.
- Do not write `OrderIntent` rows.
- Do not use consensus `score` as a regime token.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/board_briefing.py`
- Create: `tests/dq/stages/test_board_briefing.py`

## Interface

```python
def portfolio_briefing_from_research_board(board: TwelveXResearchBoard) -> dict[str, str]: ...
```

Implementation:

```python
def portfolio_briefing_from_research_board(board: TwelveXResearchBoard) -> dict[str, str]:
    digest = fx_daily_digest_to_research_digest(board.digest)
    return portfolio_briefing_from_research_digest(digest)
```

That chains P0.3 and P1.2. The fx adapter sets `regime_label=""`, and the briefing helper omits a blank regime. The result has keys `date` and `body` only.

## Steps

### 1. Implement `board_briefing.py` with the two imports and the function above. No other logic.

### 2. Tests

1. Board from `parse_research_board` with `run_date=2026-09-29`, digest summary `"Dollar bid."`, `key_themes=["rates"]`, empty lists. Briefing equals:

```python
{
    "date": "2026-09-29",
    "body": "Dollar bid.\n\n## Key themes\n\n- rates",
}
```

2. `"regime_label" not in briefing` even if a consensus row with `score=1.5` is on the board.
3. AST scan of `board_briefing.py`: no import of `digiquant.portfolio.graph`, `digiquant.portfolio.chain`, `digiquant.execution`, or `digiquant.brokers`.
4. Source of `board_briefing.py` does not contain `graph.invoke` or `OrderIntent`.

`pytestmark = pytest.mark.unit`.

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_board_briefing.py -q
ruff check digiquant/src/digiquant/stages/adapters/board_briefing.py tests/dq/stages/test_board_briefing.py
ruff format --check digiquant/src/digiquant/stages/adapters/board_briefing.py tests/dq/stages/test_board_briefing.py
git add digiquant/src/digiquant/stages/adapters/board_briefing.py tests/dq/stages/test_board_briefing.py
git commit -m "feat(digiquant): portfolio briefing from a twelve-x research board"
```

## Acceptance checklist

- [ ] Body matches the fx digest adapter, including the key-themes heading.
- [ ] Consensus scores do not appear in the dict.
- [ ] No portfolio graph import.
- [ ] No execution import.

## Dependencies

- Blocked by: P0.3, P1.2, P2.1.
- Unblocks: nothing else in this epic.

## Out of scope / do not touch

- Calling the house chain on this dict.
- Persisting a digest into `daily_snapshots`.
- Execution, brokers, twelve-x writer, SQL.
