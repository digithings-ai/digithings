"""The digisearch image's installed extras are a decision, so they get a test.

`digisearch/Dockerfile` installs exactly one extra set — `[server,ingestion,azure,
chroma,web-search]` — and it is the *only* place that set is written down outside a
comment. Nothing derives it from `pyproject.toml`, and nothing checks it. So the two
failure directions were both silent until this file:

- dropping `digillm` from the `[embedding]` extra (`build(digisearch): declare digillm
  …` did add it, but nothing would have noticed the removal), and
- adding `digillm` — as an extra on the install line, or as a fifth
  `uv pip install -e ./digillm` sibling — which would reopen the remote-embedding path
  the board deliberately kept out of the container (DIG-1407).

So this derives the installed set from the Dockerfile rather than restating it, and
pins the two decisions the board made: digillm is *declared* in `[embedding]`, and
digillm is *not installed anywhere* in the image. Comments in a Dockerfile are not a
constraint; this is.

The absent-extras registry below is the other half. `[embedding]`,
`[embedding-multilingual]`, `[rerank]`, `[pgvector]`, `[lightrag]`, `[agent]`,
`[edgar-corpus]`, `[dev]`, `[otel]` and `[all]` are all declared and all absent from the
image, which is correct — but "correct by nobody writing it down" is how a new extra
gets added to `pyproject.toml` and silently ships uninstalled, or an existing one gets
deleted from the registry and silently ships uninstalled too. The assertion is set
equality in both directions, and every entry carries a sentence saying why, so neither
half can move quietly.

Deliberately not asserted: that the image *works*. Docker Desktop is unavailable here
and in CI (the `e2e` job is `continue-on-error: true`), so this file checks the
declaration, not the build.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIGISEARCH = REPO_ROOT / "digisearch"
PYPROJECT = DIGISEARCH / "pyproject.toml"
DOCKERFILE = DIGISEARCH / "Dockerfile"

#: The extras the service image installs. Exact-set, not a floor: adding one changes the
#: image, dropping one breaks it, and both are worth a reviewer's eyes.
IMAGE_EXTRAS = frozenset({"server", "ingestion", "azure", "chroma", "web-search"})

#: Every extra `pyproject.toml` declares that the image does not install, and why. An
#: extra may leave this registry only by joining `IMAGE_EXTRAS` (and the Dockerfile), or
#: by being deleted from `pyproject.toml` with the reason removed too.
ABSENT_FROM_IMAGE: dict[str, str] = {
    "embedding": "openai + digillm: the remote embedding path, which the board ruled the "
    "image does not need (DIG-1407). Declared so a consumer that does need it can ask.",
    "embedding-multilingual": "onnxruntime + tokenizers + a HuggingFace download at first "
    "use. The image ships the default MiniLM/chroma path instead.",
    "rerank": "sentence-transformers pulls torch. The image runs no cross-encoder reranker.",
    "pgvector": "psycopg needs a reachable Postgres; the image talks to Chroma and Azure.",
    "lightrag": "the graph upgrade path, and it pulls [pgvector]. Phase 2, not shipped.",
    "agent": "langgraph: the orchestration surface digisearch exposes tools *to*.",
    "edgar-corpus": "datasets: an offline corpus bake-off, not a runtime dependency.",
    "dev": "folds in [server] + [ingestion] for a checkout's own test run. The image "
    "installs the two extras it needs directly.",
    "otel": "digibase[otel]: tracing is configured per deployment, not baked into the image.",
    "all": "the umbrella extra. Installing it into the image would pull every absent extra "
    "above, which is the opposite of each reason here.",
}

_INSTALL_LINE = re.compile(r"^\s*RUN\s.*\bpip\s+install\b")
#: `uv pip install --system -e ".[a,b]"` — the digisearch install itself. Sibling installs
#: are `"./digibase"`-style paths, so `.[...]` with nothing between the dot and the bracket
#: is what separates the service install from the workspace siblings.
_EDITABLE_SELF = re.compile(r"""-e\s*["']\.(?:\[(?P<extras>[^\]]*)\])?["']""")
_DIGILLM_TOKEN = re.compile(r"\bdigillm\b")

pytestmark = pytest.mark.unit


def _install_lines() -> list[str]:
    """Every `RUN … pip install …` line, comments excluded.

    Comment lines are skipped rather than the whole file being grepped: the Dockerfile
    explains at length why digillm is *not* a sibling, and those words must not read as
    an installation.
    """
    lines = []
    for raw in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if _INSTALL_LINE.match(raw):
            lines.append(stripped)
    assert lines, f"{DOCKERFILE.name} installs nothing — did the invocation change?"
    return lines


def _image_extras() -> set[str]:
    """The extras on digisearch's own `-e` install line."""
    found: set[str] = set()
    self_installs = 0
    for line in _install_lines():
        match = _EDITABLE_SELF.search(line)
        if match is None:
            continue
        self_installs += 1
        extras = match.group("extras") or ""
        found.update(part.strip() for part in extras.split(",") if part.strip())
    assert self_installs == 1, (
        f"{DOCKERFILE.name} has {self_installs} `-e .` installs of digisearch itself; "
        f"exactly one is expected, so the installed extras have a single source"
    )
    return found


def _declared_extras() -> dict[str, list[str]]:
    """Every extra `pyproject.toml` declares, mapped to its requirements."""
    extras: dict[str, list[str]] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return extras["project"]["optional-dependencies"]


def test_image_installs_exactly_the_expected_extras() -> None:
    declared = _declared_extras()
    installed = _image_extras()
    assert installed == IMAGE_EXTRAS, (
        f"{DOCKERFILE.name} installs {sorted(installed)}, expected {sorted(IMAGE_EXTRAS)}. "
        f"Either update the install line deliberately (and IMAGE_EXTRAS with it) or "
        f"revert it — an extra appearing or vanishing in the deployed image is a "
        f"packaging decision, not an edit."
    )
    unknown = sorted(installed - declared.keys())
    assert not unknown, (
        f"{DOCKERFILE.name} installs extras pyproject.toml does not declare: {unknown}"
    )


def test_every_extra_not_in_the_image_carries_a_named_reason() -> None:
    """No extra may be declared-and-absent without a sentence saying why.

    Set equality, both directions: a new extra lands in `pyproject.toml` and fails until
    someone says whether it ships; a deleted extra fails until its reason goes with it.
    """
    absent = set(_declared_extras()) - IMAGE_EXTRAS
    assert absent == set(ABSENT_FROM_IMAGE), (
        f"extras declared but not installed in {DOCKERFILE.name} are {sorted(absent)}, "
        f"ABSENT_FROM_IMAGE documents {sorted(ABSENT_FROM_IMAGE)}. "
        f"New: {sorted(absent - ABSENT_FROM_IMAGE)} (add a reason, or install it). "
        f"Stale: {sorted(ABSENT_FROM_IMAGE - absent)} (delete the extra, or the reason)."
    )
    thin = sorted(name for name, reason in ABSENT_FROM_IMAGE.items() if len(reason) < 40)
    assert not thin, f"these reasons are placeholders, not reasons: {thin}"


def test_digillm_is_declared_in_the_embedding_extra() -> None:
    """The declaration side of the DIG-1407 decision.

    `digisearch` calls `digillm.client` on its web-research and websets paths behind lazy
    import guards. The guards made the missing declaration invisible: nothing imported
    digillm at module scope, so an undeclared dependency ran fine locally (digillm is a
    workspace sibling on the dev `pythonpath`) and failed only inside a consumer's
    install. Asserting the declaration is what makes removing it a failure.
    """
    embedding = _declared_extras()["embedding"]
    digillm_requirements = [req for req in embedding if _DIGILLM_TOKEN.search(req)]
    assert digillm_requirements, (
        "the [embedding] extra no longer declares digillm, so the web-research and websets "
        "call sites behind their import guards are undeclared again (DIG-1407)"
    )


def test_web_search_does_not_pull_the_digillm_client() -> None:
    """Pin the gating extra named in the `[embedding]` comment.

    The comment says the digillm call sites sit on the optional web path, whose gating
    extra is `[web-search]` — and that `[web-search]` does *not* pull `[embedding]`. That
    is a real runtime gap, not a documentation nicety: a consumer installing
    `digisearch[web-search]` gets the web path without a digillm client, hits the guard,
    and gets `WebResearchError`. If `[web-search]` ever grows `digisearch[embedding]` or a
    `digillm` requirement, that gap closes and the comment above it becomes wrong.
    """
    web_search = _declared_extras()["web-search"]
    assert not any(_DIGILLM_TOKEN.search(req) for req in web_search), (
        f"[web-search] now requires digillm ({web_search}); the [embedding] comment's "
        f"claim that web-search does not pull it is stale"
    )
    assert not any(req.startswith("digisearch[embedding") for req in web_search), (
        f"[web-search] now pulls the embedding extra ({web_search}); the [embedding] "
        f"comment's claim that web-search does not pull it is stale"
    )


def test_digillm_is_not_installed_anywhere_in_the_digisearch_image() -> None:
    """The installation side of the DIG-1407 decision — the one that costs money.

    The board ruled that the deployed image does not need the remote embedding path.
    Installing digillm here would drag `openai` in with it and make that path importable
    for the first time. Both routes are covered: an extra on digisearch's own install
    line, and a fifth `uv pip install -e ./digillm` sibling.
    """
    offenders = [line for line in _install_lines() if _DIGILLM_TOKEN.search(line)]
    assert not offenders, (
        f"{DOCKERFILE.name} installs digillm: {offenders}. DIG-1407 keeps it out of the "
        f"deployed image — digillm's hard deps would drag openai in and enable the remote "
        f"embedding path the board declined. Remove the line, not the comment explaining "
        f"it is absent."
    )
