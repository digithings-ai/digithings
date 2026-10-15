"""Skill documents for digigraph: one folder per skill, read at call time.

DIG-2637. A *skill document* is a block of instructions the agent fetches with
the ``get_skill`` tool call, so nothing is baked into the prompt. It is
deliberately not the tool bundle in ``digigraph.skills.registry``: that is a
named list of tool names with an optional ``when`` gate and has no body to
read. Both are called "skill", so they live in different packages rather than
sharing one directory where the word would mean two incompatible things.

Layout — ``skill_library/<name>/SKILL.md`` with YAML frontmatter::

    ---
    name: present-results
    description: One line, shown to the model by list_skills.
    version: "1"
    ---

    the instructions, in markdown

The folder name and the frontmatter ``name`` must agree: one id per skill, no
aliases. A reader grepping the tree and a caller passing the tool argument then
always land on the same folder, which is what makes a skill's id citable.

What a document may contain is a product decision, not an oversight. The
grounding rule (DIG-100, DIG-509 G1', and the canonical text owned by
``docs/digichat/no-invent-guard.md``) holds that a source-or-refuse rule that
also enumerates capabilities is the defect it exists to prevent, because an
inventory read from configuration goes stale and the agent presents it as
fact. These documents are handed to a client-visible agent, so they name no
tool, no retrieval surface, no collection and no customer. ``tests/dg/
test_skill_library.py`` pins that absence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILL_LIBRARY_DIR = Path(__file__).resolve().parent
SKILL_FILENAME = "SKILL.md"

# Kebab-case id. Deliberately narrow: this pattern is the ONLY thing standing
# between a caller-supplied string and a filesystem join (see load_skill_document),
# so it admits no dots, no slashes and no leading or trailing separator.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(?P<meta>.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
_REQUIRED_FRONTMATTER = ("name", "description")


class SkillDocumentError(RuntimeError):
    """A skill folder exists but is not a readable skill document.

    Distinct from "no such skill". A missing folder is an ordinary lookup miss
    the caller can recover from; a malformed one is a packaging fault, and it
    raises rather than being silently skipped so it cannot ship as an agent
    that quietly never sees the skill it was given.
    """


@dataclass(frozen=True)
class SkillDocument:
    """One SKILL.md, parsed. ``body`` is everything after the frontmatter."""

    name: str
    description: str
    body: str
    version: str | None
    source: str

    def as_summary(self) -> dict[str, str | None]:
        """The list_skills projection: name and description only.

        A description is the only part the model sees before it fetches the
        document, so it carries no body and no path.
        """
        return {"name": self.name, "description": self.description}


def _parse_frontmatter(text: str, source: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise SkillDocumentError(f"{source}: no YAML frontmatter block")
    try:
        meta = yaml.safe_load(match.group("meta")) or {}
    except yaml.YAMLError as exc:
        raise SkillDocumentError(f"{source}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillDocumentError(
            f"{source}: frontmatter must be a mapping, got {type(meta).__name__}"
        )
    clean: dict[str, str] = {}
    for key, value in meta.items():
        if not isinstance(key, str) or value is None:
            continue
        clean[key] = str(value).strip()
    return clean, text[match.end() :]


def _read_document(folder: Path) -> SkillDocument:
    source = f"skill_library/{folder.name}/{SKILL_FILENAME}"
    try:
        text = (folder / SKILL_FILENAME).read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillDocumentError(f"{source}: unreadable: {exc}") from exc

    meta, body = _parse_frontmatter(text, source)

    missing = [key for key in _REQUIRED_FRONTMATTER if not meta.get(key)]
    if missing:
        raise SkillDocumentError(f"{source}: frontmatter missing {', '.join(missing)}")
    name = meta["name"]
    if not SKILL_NAME_RE.match(name):
        raise SkillDocumentError(
            f"{source}: name {name!r} is not kebab-case (lower-case words joined by single hyphens)"
        )
    if name != folder.name:
        raise SkillDocumentError(
            f"{source}: frontmatter name {name!r} does not match its folder — "
            "one id per skill, no aliases"
        )
    if not body.strip():
        raise SkillDocumentError(f"{source}: no instructions after the frontmatter")

    return SkillDocument(
        name=name,
        description=meta["description"],
        body=body.strip(),
        version=meta.get("version"),
        source=source,
    )


def skill_folders() -> list[Path]:
    """Every folder in the library, sorted, whether or not it parses."""
    if not SKILL_LIBRARY_DIR.is_dir():  # pragma: no cover - installed layout
        return []
    return sorted(p for p in SKILL_LIBRARY_DIR.iterdir() if p.is_dir())


def list_skill_documents() -> list[SkillDocument]:
    """Every skill document in the library, sorted by name.

    Raises on the first malformed folder rather than skipping it: a folder
    without a SKILL.md is simply not a skill, but one with a broken SKILL.md is
    a packaging fault and must not be invisible to the agent or to this code.
    """
    documents = []
    for folder in skill_folders():
        if not (folder / SKILL_FILENAME).is_file():
            continue
        documents.append(_read_document(folder))
    return sorted(documents, key=lambda doc: doc.name)


def load_skill_document(name: str) -> SkillDocument:
    """Read one skill document by id.

    The id is validated against SKILL_NAME_RE *before* it reaches the
    filesystem: it carries no dot, no slash and no separator, so the join
    below cannot escape skill_library.
    """
    if not isinstance(name, str) or not SKILL_NAME_RE.match(name):
        raise SkillDocumentError(f"{name!r} is not a valid skill id")
    folder = SKILL_LIBRARY_DIR / name
    if not (folder / SKILL_FILENAME).is_file():
        raise SkillDocumentError(f"unknown skill: {name}")
    return _read_document(folder)


def known_skill_names() -> list[str]:
    return [doc.name for doc in list_skill_documents()]
