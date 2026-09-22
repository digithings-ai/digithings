"""portfolio skill-file loader.

Mirrors :mod:`digiquant.research.skills` but resolves paths under
``digiquant/src/digiquant/portfolio/skills/``. Each engine's ``load_skill()`` only finds
its own skills — research cannot resolve portfolio-side analyst / debate / PM
skills and vice versa. See [ADR-0015](../../../../docs/adr/0015-research-vs-portfolio.md).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# Re-export the shared exception types from research's loader so callers can
# catch a single class regardless of which engine raised. portfolio's loader
# is a path-only fork; the parser logic is intentionally identical.
from digiquant.research.skills import (
    EDIT_SCHEMA_CONSTRAINTS,
    MalformedFrontmatterError,
    SkillNotFoundError,
    _split_frontmatter,
)

_DELIBERATION_SKILLS = frozenset({"deliberation", "deliberation-analyst-response"})

DELIBERATION_AMENDMENT_CONTRACT = """\
## Forecast amendment (only when the debate changed the economics)

``forecast_amendment`` is an optional **complete replacement** ``ForecastTerms``, not a
patch. Emit it only when this debate actually changed the scenario economics. If the
analyst's terms still stand, omit the field entirely — do not send a partial object or an
empty one.

A partial or malformed amendment is **rejected outright**: the whole debate is discarded
and the ticker silently carries the analyst stance, so a wrong amendment is worse than no
amendment.

When you do emit it, send every one of these fields as a complete object:

- ``bear_return``, ``base_return``, ``bull_return`` — scenario returns as **fractions**
  (``-0.15``, not ``-15`` and not ``-15%``), ordered ``bear <= base <= bull``.
- ``bear_probability``, ``base_probability``, ``bull_probability`` — non-negative and
  summing to **exactly** ``1.0``. The system never renormalises: if they do not sum to 1
  the amendment is rejected.
- ``thesis_valid_probability`` — probability the analyst's thesis holds.
- ``raw_uncertainty`` — exactly one of ``low``, ``medium``, ``high``.
- ``horizon_sessions``, ``half_life_sessions`` — positive counts of **trading sessions**.
  You may omit these two; the system copies them from the analyst's base forecast. They are
  identity, not new economics — never restate them as calendar days.
- ``evidence_ids``, ``counter_evidence_ids``, ``assumptions``, ``invalidation_rules`` —
  optional lists. Do not invent IDs or timestamps; the system materializes identity.

**Do not invent field names.** ``ForecastTerms`` has no price levels, entry triggers,
targets, or conviction fields — an extra key such as ``conditional_entry`` or
``convision_score`` rejects the whole object. Express the view through the scenario
returns, the scenario probabilities, ``thesis_valid_probability`` and ``raw_uncertainty``.
"""

DELIBERATION_TOOL_USE_CONTRACT = """\
## Tools (read this before you plan a single call)

Your toolset is exactly the functions listed in this request's tool schemas — nothing else.
There is no shell, no URL fetcher, and no MCP client in this loop. If an instruction names
one, it cannot be run here.

- The analyst's document for this ticker and today's digest are **already provided** in
  SHARED_CONTEXT. Read them there; do not fetch your own analysis back out of the store.
- Every retrieval tool is a read of stored rows: repeating a call with the same arguments
  returns the same bytes, and re-phrasing the question cannot surface a row that was not
  already there. An empty result is an answer, not a failure to retry.
- Use as many calls as this meeting genuinely needs to test the analyst's claims — then
  converge. This is a conversation: challenge, answer, close. Spend the turn on the
  argument, not on re-querying evidence you already hold.
"""

__all__ = [
    "DELIBERATION_AMENDMENT_CONTRACT",
    "DELIBERATION_TOOL_USE_CONTRACT",
    "MalformedFrontmatterError",
    "SkillNotFoundError",
    "list_skill_slugs",
    "load_skill",
    "load_skill_edit",
    "load_skill_full",
    "load_skill_with_frontmatter",
]


def _portfolio_data_root() -> Path:
    """Return ``digiquant/src/digiquant/portfolio/`` (the portfolio package dir).

    Skills + templates live alongside the package code so they ship inside
    the wheel via ``[tool.setuptools.package-data]`` (#486).
    """
    return Path(__file__).resolve().parent


def _skill_path(slug: str) -> Path:
    return _portfolio_data_root() / "skills" / slug / "SKILL.md"


def _skill_edit_path(slug: str) -> Path:
    return _portfolio_data_root() / "skills" / slug / f"{slug}-edit.md"


def _skill_full_path(slug: str) -> Path:
    return _portfolio_data_root() / "skills" / slug / f"{slug}-full.md"


def _skill_full_candidates(slug: str) -> tuple[Path, ...]:
    """Resolve ``*-full.md`` for a slug, including nested family files.

    Conventional path is ``skills/<slug>/<slug>-full.md``. Hyphenated slugs may
    also live beside a parent skill: ``deliberation-analyst-response`` reads
    ``skills/deliberation/analyst-response-full.md`` (deliberation reply; not analyst).
    """
    root = _portfolio_data_root() / "skills"
    paths = [root / slug / f"{slug}-full.md"]
    if "-" in slug:
        family, rest = slug.split("-", 1)
        paths.append(root / family / f"{rest}-full.md")
    paths.append(root / slug / "SKILL.md")
    return tuple(paths)


@lru_cache(maxsize=64)
def load_skill_full(slug: str) -> str:
    """Return the Markdown body of a portfolio full skill (see ``_skill_full_candidates``).

    The deliberation turn contract (#4513) is appended for the two debate slugs here at
    the single load chokepoint rather than copied into each file, for the same reason
    ``EDIT_SCHEMA_CONSTRAINTS`` is appended in ``load_skill_edit``: it cannot drift
    between them.
    """
    last = _skill_full_path(slug)
    for path in _skill_full_candidates(slug):
        last = path
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
            _, body = _split_frontmatter(raw)
            parts = [body.strip()]
            if slug in _DELIBERATION_SKILLS:
                parts.extend((DELIBERATION_AMENDMENT_CONTRACT, DELIBERATION_TOOL_USE_CONTRACT))
            return "\n\n".join(parts)
    raise SkillNotFoundError(f"full skill not found: {slug!r} (expected at {last})")


@lru_cache(maxsize=64)
def load_skill_edit(slug: str) -> str:
    """Return the Markdown body of ``skills/<slug>/<slug>-edit.md``.

    The shared DocumentPatch limits are appended here too (#1740) — portfolio
    analyst/thesis edit turns emit the same patch schema and hit the same
    240-char ``reason`` cap (it took out the analyst asset-analyst run on 2026-07-24).
    """
    path = _skill_edit_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"edit skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return f"{body.strip()}\n\n{EDIT_SCHEMA_CONSTRAINTS}"


@lru_cache(maxsize=64)
def load_skill(slug: str) -> str:
    """Return the Markdown body of ``digiquant/src/digiquant/portfolio/skills/<slug>/SKILL.md``."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return body.strip()


def load_skill_with_frontmatter(slug: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter, body) for a portfolio-side skill file."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    return _split_frontmatter(raw)


def list_skill_slugs() -> list[str]:
    """Return every slug for which ``digiquant/src/digiquant/portfolio/skills/<slug>/SKILL.md`` exists. Sorted."""
    root = _portfolio_data_root() / "skills"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
