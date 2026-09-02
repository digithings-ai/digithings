"""Skill-file loader.

A skill is a ``skills/<slug>/SKILL.md`` under ``digiquant/src/digiquant/olympus/atlas/skills/``.
The file has YAML frontmatter (``name``, ``description``) followed by Markdown
instructions. Only the Markdown body is relevant at inference time; the
frontmatter exists for human catalog tooling.

Design:
- One function, ``load_skill(slug)``, returns the body as a string.
- Optional ``load_skill_with_frontmatter`` returns (frontmatter_dict, body)
  for code paths that need both (e.g. the skills catalog CI check in #176's
  commit 9).
- Skills directory is resolved relative to the ``digiquant/``
  package root so tests + production use the same path.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


class SkillNotFoundError(FileNotFoundError):
    """Raised when ``skills/<slug>/SKILL.md`` is missing.

    Separate exception type so callers (triage, phase wiring) can distinguish
    'skill missing' from other I/O errors and fail loudly with a usable message.
    """


def _atlas_data_root() -> Path:
    """Return the directory holding Atlas skills + templates + config.

    Skills, templates, and config live alongside the Atlas package code
    (``digiquant/src/digiquant/olympus/atlas/{skills,templates,config}/``) so they
    ship inside the wheel via ``[tool.setuptools.package-data]``. See
    [#486](https://github.com/digithings-ai/digithings/issues/486).
    """
    return Path(__file__).resolve().parent


def _skill_path(slug: str) -> Path:
    return _atlas_data_root() / "skills" / slug / "SKILL.md"


def _skill_edit_path(slug: str) -> Path:
    return _atlas_data_root() / "skills" / slug / f"{slug}-edit.md"


# Limits the DocumentPatch schema enforces but that none of the 17 *-edit.md
# skills stated (#1740). The model overran the 240-char `reason` cap regularly,
# and because it is a hard schema constraint a single long reason raised
# ValidationError and discarded the WHOLE patch — costing 1-4 researched
# segments per run, and the master digest itself on 2026-07-28.
#
# Appended at the single load chokepoint rather than copied into 17 heterogeneous
# files, so it cannot drift between them. Keep in sync with
# digiquant.olympus.edit_mode.models.PatchOp / DocumentPatch — there is a test
# asserting path caps and that reason/summary have no max_length (#1740 / #3063).
EDIT_SCHEMA_CONSTRAINTS = """## Output constraints (schema-enforced)

- `ops[].path` — 512 characters maximum; an RFC 6901 JSON Pointer starting `/`.
- `ops[].reason` and `one_line_summary` — free prose with **no** character
  maximum. A previous 240/400-char hard cap discarded entire patches (#1740);
  do not invent a limit or truncate these fields."""


# Skills that must not receive RESEARCH_MEMO_RULES (Phase 1–5 memo skeleton).
# Digest + digest-subsection get DIGEST_BRIEFING_RULES instead.
_NON_RESEARCH_MEMO_SKILLS = frozenset(
    {
        "digest",
        "digest-subsection",
        "beliefs-distillation",
        "monthly-synthesis",
        "decision-reflector",
    }
)

_DIGEST_BRIEFING_SKILLS = frozenset({"digest", "digest-subsection"})


def _is_research_memo_skill(slug: str) -> bool:
    return slug not in _NON_RESEARCH_MEMO_SKILLS


# Appended to EVERY skill, full and edit alike (#1750). Deliberately at the single load
# chokepoint rather than copied into 20 heterogeneous SKILL.md files, for the same reason
# EDIT_SCHEMA_CONSTRAINTS is: it cannot drift between them.
#
# Both variants get it because the defect appeared on the FULL path. The frozen
# `sector-healthcare` block that opened #1750 — "XLV is at $162.16, up 5.46% from its 50-day
# SMA" — was produced by the 2026-07-26 *baseline* run, which forces `resolve_edit_mode → full`
# and never calls `merge_document_patch`. An edit-only rule would have missed it entirely.
#
# Two separate failures are being addressed, and only the first is fixable here:
#   * a number quoted with no date, so a reader cannot tell a current figure from one carried
#     for eleven publication dates;
#   * a number that was never in the data at all — $162.16 was not an XLV close or intraday
#     print on 2026-07-23 when it first appeared, and the payload attributed it to
#     `price_technicals:XLV` via `source_ids`, which is worse than no attribution. Dating a
#     fabricated number does not make it true. Detecting that needs a numeric-fidelity
#     validator cross-checking prose against `price_technicals`; the instruction below only
#     makes the claim auditable.
# Appended to every Phase 1–5 skill (full and edit). The JSON skeleton used to
# win over the markdown templates already in the skills; this block is the
# contract the renderer and digest slim assume.
RESEARCH_MEMO_RULES = """## Research memo (required)

Write a markdown `body` — that is the operator artifact, not a JSON dump.

Suggested skeleton (variable depth is allowed; skip empty sections):

```markdown
# {Topic} — {as-of date of the data}

## {Topical heading 1}
Prose with inline [title](url) citations.

## {Topical heading 2}
…
```

Use 2–5 topical `##` sections that fit today's evidence. Do **not** invent
data-quality or confidence scores. Do **not** emit a Signals section. Do **not**
print `Bias:` at the top. Optional `internal_bias` is a non-rendered token for
digest/triage only. `sources` is grounding, not an appendix dump."""


DIGEST_BRIEFING_RULES = """## Digest briefing (required)

Write a markdown `body` — that is the operator artifact, not a JSON dump of
bias / headline / Signals / confidence / data_quality.

This is a long analyst-entry briefing. Length is allowed. Use topical `##`
headings and inline `[title](url)` citations.

Do **not** emit `**Overall bias:**`, a Signals section, data-quality grades, or
confidence floats. Optional `regime_label` is a short chip token, not a
rendered metric."""


QUANTITATIVE_FINDING_RULES = """## Dating your numbers (required)

Every figure you quote in the markdown body must carry the date of the DATA — not the date of this run.

- Name the date inline when you quote a number: `SPY flat at $738.93 (2026-07-24)`.
- That date is the date of the row you read from the tool. If the latest `price_technicals` row
  is 2026-07-30 because today's close has not landed yet, write `2026-07-30` — do NOT write
  today's date.
- **Never carry a number forward from the prior document without re-reading it.** If you cannot
  re-verify a figure from a tool on this run, drop it or state the older date it came from. A
  stale number under a fresh date is the specific failure this rule exists to stop.
- Quote only figures you actually read from a tool this run. An inline `[title](url)` (or a
  `sources` id) is an assertion that the named source contains the number — attributing an
  unverified figure is worse than leaving it unsourced."""


class MalformedFrontmatterError(ValueError):
    """Raised when a SKILL.md starts with ``---`` but has a broken YAML block."""


def _split_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter_dict, body).

    - No frontmatter (no leading ``---``) → ``({}, raw)``.
    - Well-formed YAML frontmatter → parsed dict + body.
    - Opening ``---`` but missing closing fence, or non-dict YAML → raise
      :class:`MalformedFrontmatterError`. Silent fallback would mask
      authoring errors in skill files, so the loader now fails loud.
    """
    text = raw.lstrip()
    if not text.startswith("---"):
        return {}, raw
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise MalformedFrontmatterError("frontmatter starts with '---' but no closing fence found")
    frontmatter_src = parts[1]
    body = parts[2].lstrip("\n")
    meta = yaml.safe_load(frontmatter_src) or {}
    if not isinstance(meta, dict):
        raise MalformedFrontmatterError(
            f"frontmatter must be a YAML mapping, got {type(meta).__name__}"
        )
    return meta, body


@lru_cache(maxsize=64)
def load_skill(slug: str) -> str:
    """Return the Markdown body of ``skills/<slug>/SKILL.md``.

    Cached — skill bodies are static per process.

    :data:`QUANTITATIVE_FINDING_RULES` is appended (#1750). The full path needs it as much as
    the edit path does: the frozen XLV block that opened #1750 was produced by a *baseline* run.
    """
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    parts = [body.strip()]
    if _is_research_memo_skill(slug):
        parts.append(RESEARCH_MEMO_RULES)
    if slug in _DIGEST_BRIEFING_SKILLS:
        parts.append(DIGEST_BRIEFING_RULES)
    parts.append(QUANTITATIVE_FINDING_RULES)
    return "\n\n".join(parts)


@lru_cache(maxsize=64)
def load_skill_edit(slug: str) -> str:
    """Return the Markdown body of ``skills/<slug>/<slug>-edit.md``.

    Used by Atlas edit-mode nodes (spec §5.6). Separate cache from
    :func:`load_skill` so full and edit variants can coexist.

    :data:`EDIT_SCHEMA_CONSTRAINTS` is appended to every edit skill (#1740), and
    :data:`QUANTITATIVE_FINDING_RULES` to every skill of either kind (#1750).
    """
    path = _skill_edit_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"edit skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    parts = [body.strip()]
    if _is_research_memo_skill(slug):
        parts.append(RESEARCH_MEMO_RULES)
    if slug in _DIGEST_BRIEFING_SKILLS:
        parts.append(DIGEST_BRIEFING_RULES)
    parts.extend((EDIT_SCHEMA_CONSTRAINTS, QUANTITATIVE_FINDING_RULES))
    return "\n\n".join(parts)


def load_skill_with_frontmatter(slug: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter, body). Used by catalog / drift-check tooling."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    return _split_frontmatter(raw)


def list_skill_slugs() -> list[str]:
    """Return every slug for which ``skills/<slug>/SKILL.md`` exists. Sorted."""
    root = _atlas_data_root() / "skills"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
