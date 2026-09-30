# P0.3 — fx daily digest → ResearchDigest

**Lane:** OpenCode free implement.

**Parent:** #4762.

## Goal

`fx_daily_digest_to_research_digest` maps one hub `fx_daily_digest` row into a `ResearchDigest` with `source="twelve-x.research"` and `composition_id="twelve-x"`. `regime_label` stays empty. Themes become a markdown list under the summary. No database call.

## Non-goals

- Do not read Supabase.
- Do not invent a regime label from scores or themes.
- Do not map briefs, the ledger, or events (P2.1).
- Do not emit trade ideas.

## Files

- Create: `digiquant/src/digiquant/stages/adapters/fx_digest.py`
- Create: `tests/dq/stages/test_fx_digest_adapter.py`
- Modify: `digiquant/src/digiquant/stages/adapters/__init__.py` only if you add a re-export. Prefer leaving it import-free. Callers import `digiquant.stages.adapters.fx_digest`.

Depends on P0.1 types: `ResearchDigest`.

## Interfaces

```python
class FxDailyDigestInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    run_date: date
    summary: str
    key_themes: list[str] | str | None = None
    doc_count: int = 0
    broker_count: int = 0

def normalize_key_themes(raw: list[str] | str | None) -> list[str]: ...

def fx_daily_digest_to_research_digest(row: FxDailyDigestInput) -> ResearchDigest: ...
```

`doc_count` and `broker_count` are accepted so a hub row validates. They are not copied into `ResearchDigest` (the digest model has no such fields). Do not add them.

## Steps

### 1. Implement `fx_digest.py`

```python
"""Map an ``fx_daily_digest`` reader row onto ``ResearchDigest``."""

from __future__ import annotations

from datetime import date

from digiquant.stages.contracts import ResearchDigest
from pydantic import BaseModel, ConfigDict


class FxDailyDigestInput(BaseModel):
    """Fields the hub reads from ``fx_daily_digest`` (``types.ts``)."""

    model_config = ConfigDict(extra="ignore")

    run_date: date
    summary: str
    key_themes: list[str] | str | None = None
    doc_count: int = 0
    broker_count: int = 0


def normalize_key_themes(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _body(summary: str, themes: list[str]) -> str:
    text = summary.strip()
    if not themes:
        return text
    bullets = "\n".join(f"- {theme}" for theme in themes)
    if text:
        return f"{text}\n\n## Key themes\n\n{bullets}"
    return f"## Key themes\n\n{bullets}"


def fx_daily_digest_to_research_digest(row: FxDailyDigestInput) -> ResearchDigest:
    body = _body(row.summary, normalize_key_themes(row.key_themes))
    if not body.strip():
        raise ValueError("fx_daily_digest row has an empty summary and no themes")
    return ResearchDigest(
        run_date=row.run_date,
        body=body,
        regime_label="",
        source="twelve-x.research",
        composition_id="twelve-x",
    )
```

### 2. Tests (`pytestmark = pytest.mark.unit`)

1. Row `run_date=2026-09-29`, `summary="Dollar bid."`, `key_themes=["rates", "oil"]`, `doc_count=4`, `broker_count=3` → body is `Dollar bid.\n\n## Key themes\n\n- rates\n- oil`, regime `""`, source `twelve-x.research`, composition `twelve-x`.
2. `key_themes` as one string `"rates"` → a single bullet `- rates`.
3. `key_themes=None` and summary `"Only summary."` → body is `Only summary.` with no `Key themes` heading.
4. Empty summary and empty themes raises `ValueError` matching `empty summary`.
5. Extra key `writer_version="x"` on the input model is ignored (`extra="ignore"`).
6. `doc_count` is not an attribute of the returned `ResearchDigest` (`"doc_count" not in digest.model_dump()`).

### 3. Run and commit

```bash
pytest -m unit tests/dq/stages/test_fx_digest_adapter.py -q
ruff check digiquant/src/digiquant/stages/adapters/fx_digest.py tests/dq/stages/test_fx_digest_adapter.py
ruff format --check digiquant/src/digiquant/stages/adapters/fx_digest.py tests/dq/stages/test_fx_digest_adapter.py
git add digiquant/src/digiquant/stages/adapters/fx_digest.py tests/dq/stages/test_fx_digest_adapter.py
git commit -m "feat(digiquant): map fx daily digest rows to ResearchDigest"
```

## Acceptance checklist

- [ ] Source is `twelve-x.research` and composition is `twelve-x`.
- [ ] `regime_label` is always `""` on this adapter.
- [ ] No import of `digiquant.execution`, `digiquant.brokers`, or Supabase clients.
- [ ] Dashboard `types.ts` is unchanged.

## Dependencies

- Blocked by: P0.1 (`ResearchDigest`).
- Unblocks: P4.2.

## Out of scope / do not touch

- Ranking, relevance weights, strategist prompts.
- `fx_research_history` and other tables.
- Execution, brokers, cron, workflows, twelve-x repo writes.
