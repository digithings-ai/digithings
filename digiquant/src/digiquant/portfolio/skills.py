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
# Only the analyst turn model carries ``forecast_amendment``, and the debate loop reads it
# from the analyst turn alone (``deliberation.py``); a PM turn's amendment is dropped.
_DELIBERATION_AMENDMENT_SKILLS = frozenset({"deliberation-analyst-response"})

DELIBERATION_AMENDMENT_CONTRACT = """\
## Forecast amendment (only when the debate changed the economics)

``forecast_amendment`` is an optional **complete replacement** ``ForecastTerms``, not a
patch. Emit it only when this debate actually changed the scenario economics. If the
analyst's terms still stand, omit the field entirely — do not send a partial object or an
empty one.

A partial or malformed amendment is **rejected outright**: the whole debate is discarded
and the ticker silently carries the analyst stance, so a wrong amendment is worse than no
amendment.

When you do emit it, send a complete object. Every field below is required unless it
says the system fills it for you:

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

- The analyst's analysis for this ticker and the digest are **already in this request's
  inputs**. Read them there; do not fetch your own analysis back out of the store.
- Every retrieval tool is a read of stored rows: repeating a call with the same arguments
  returns the same bytes, and re-phrasing the question cannot surface a row that was not
  already there. An empty result is an answer, not a failure to retry.
- Use as many calls as this meeting genuinely needs to test the analyst's claims — then
  converge. This is a conversation: challenge, answer, close. Spend the turn on the
  argument, not on re-querying evidence you already hold.
"""

# Portfolio skills whose turn is bound to tools by the phase that loads them:
# ``tools=tools`` is passed by ``phase7d_pm`` (risk-aggressive, risk-conservative and the
# pm-* fallback chain), ``direction`` (pm-direction), ``portfolio_common`` (asset-analyst),
# ``deliberation`` (both turns) and ``thesis_common`` (thesis, thesis-vehicle-map,
# market-thesis-exploration). ``coverage-director`` is loaded with ``tools=None`` and
# ``pipeline-evolution`` is loaded tool-less, so the contract would be false for them.
_TOOL_CONTRACT_SKILLS = frozenset(
    {
        "asset-analyst",
        "deliberation",
        "deliberation-analyst-response",
        "market-thesis-exploration",
        "pm-allocation-memo",
        "pm-direction",
        "pm-rebalance-decision",
        "portfolio-manager",
        "risk-aggressive",
        "risk-conservative",
        "thesis",
        "thesis-vehicle-map",
    }
)
# The deliberation turns carry the debate-specific contract instead of this one.
_GENERAL_TOOL_CONTRACT_SKILLS = _TOOL_CONTRACT_SKILLS - _DELIBERATION_SKILLS

PORTFOLIO_TOOL_USE_CONTRACT = """\
## Tools (read this before you plan a single call)

Your toolset is exactly the functions listed in this request's tool schemas — nothing else.
There is no shell, no URL fetcher, no browser, and no MCP client in this loop. If the skill
instructions above name one, that instruction describes a different environment: you cannot
run it, so do not try, and do not report its absence as a gap in the data.

- Every retrieval tool is a read of stored rows. Repeating a call with the same arguments
  returns the same bytes, and re-phrasing the question cannot surface a row that was not
  already there. An empty result is an answer, not a failure to retry.
- Do not fetch back out of the store what this request already carries in its inputs — read
  it from the inputs.
- Data tools are ground truth where the request carries them. Use as many calls as the work
  genuinely needs to ground your claims, then converge: once they have returned you hold the
  evidence this turn is going to get. More calls do not add evidence, and a number that is
  genuinely absent from the evidence should be reported as absent, not hunted for.
"""

__all__ = [
    "DELIBERATION_AMENDMENT_CONTRACT",
    "DELIBERATION_TOOL_USE_CONTRACT",
    "PORTFOLIO_TOOL_USE_CONTRACT",
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

    Both contracts are appended here at the single load chokepoint rather than copied
    into each file, for the same reason ``EDIT_SCHEMA_CONSTRAINTS`` is appended in
    ``load_skill_edit``: it cannot drift between them. ``PORTFOLIO_TOOL_USE_CONTRACT``
    (#4524) reaches every portfolio skill whose turn is tool-grounded;
    ``DELIBERATION_AMENDMENT_CONTRACT`` reaches the analyst-reply skill only —
    ``DeliberationAnalystTurn`` is the only turn model carrying ``forecast_amendment``
    and the only one the loop reads.
    """
    last = _skill_full_path(slug)
    for path in _skill_full_candidates(slug):
        last = path
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
            _, body = _split_frontmatter(raw)
            parts = [body.strip()]
            if slug in _GENERAL_TOOL_CONTRACT_SKILLS:
                parts.append(PORTFOLIO_TOOL_USE_CONTRACT)
            if slug in _DELIBERATION_AMENDMENT_SKILLS:
                parts.append(DELIBERATION_AMENDMENT_CONTRACT)
            if slug in _DELIBERATION_SKILLS:
                parts.append(DELIBERATION_TOOL_USE_CONTRACT)
            return "\n\n".join(parts)
    raise SkillNotFoundError(f"full skill not found: {slug!r} (expected at {last})")


@lru_cache(maxsize=64)
def load_skill_edit(slug: str) -> str:
    """Return the Markdown body of ``skills/<slug>/<slug>-edit.md``.

    The shared DocumentPatch limits are appended here too (#1740) — portfolio
    analyst/thesis edit turns emit the same patch schema and hit the same
    240-char ``reason`` cap (it took out the analyst asset-analyst run on 2026-07-24).
    The tool contract (#4524) is appended for the same reason: the edit turn of a
    tool-grounded skill is tool-grounded too. It is phrased against "this request's tool
    schemas", so it stays accurate on the simulator path (``research/testing/simulator.py``)
    that reuses this loader without binding tools.
    """
    path = _skill_edit_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"edit skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    parts = [body.strip(), EDIT_SCHEMA_CONSTRAINTS]
    if slug in _GENERAL_TOOL_CONTRACT_SKILLS:
        parts.append(PORTFOLIO_TOOL_USE_CONTRACT)
    if slug in _DELIBERATION_SKILLS:
        parts.append(DELIBERATION_TOOL_USE_CONTRACT)
    return "\n\n".join(parts)


@lru_cache(maxsize=64)
def load_skill(slug: str) -> str:
    """Return the Markdown body of ``digiquant/src/digiquant/portfolio/skills/<slug>/SKILL.md``.

    ``PORTFOLIO_TOOL_USE_CONTRACT`` (#4524) is appended for tool-grounded skills, on the
    same single-chokepoint reasoning as ``load_skill_full``.
    """
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    parts = [body.strip()]
    if slug in _GENERAL_TOOL_CONTRACT_SKILLS:
        parts.append(PORTFOLIO_TOOL_USE_CONTRACT)
    if slug in _DELIBERATION_SKILLS:
        parts.append(DELIBERATION_TOOL_USE_CONTRACT)
    return "\n\n".join(parts)


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
