"""The e2e stack job must be triggered by every Dockerfile it builds.

`test-e2e.yml`'s `e2e` job is the only CI job that builds service images — it runs
`docker compose up` and Compose builds each service from its `build.dockerfile`. The
job is gated on `on.push.paths`, so a Dockerfile outside that filter is never built by
CI at all: the image change merges with nothing having compiled it.

DIG-1407 found this for `digisearch/Dockerfile` and added it to the filter. Three more
sat in the same hole — the job starts `digigraph`, and Compose pulls `digiquant`,
`digisearch` and `digikey` in behind it — so four of the five images it builds were
unwatched and the fifth was fixed by hand. Nothing tests the filter, so the next
Dockerfile lands unwatched again.

So this derives the answer instead of restating it: parse the workflow's own
`run:` blocks for the Compose services it starts and any literal `docker build`, walk
`depends_on` transitively through `docker-compose.yml`, and require a filter entry that
matches every workspace Dockerfile in that closure. Adding a dependency to a service
fails here until the filter learns about it.

Deliberately *not* asserted: that the whole compose file is covered. The e2e job starts
four services; `digivault`, `zammad-mcp` and `digichat` have builds too and this job
never touches them. Gating the filter on all of them would start the stack job on
edits that cannot affect it — the same trade `#1956` declines for `**/package.json`.
This asserts *build* inputs of the job, not install inputs of the file.

Real-time in both directions: `tests/**` and `.github/workflows/**` are both in
`ci_paths.yaml`'s `ruff_and_scripts`, which runs `pytest tests/scripts/ -m "unit or
baseline"`. So this test fires on the PR that *adds* a Dockerfile and on the PR that
*removes* a filter entry — the deletion half, which
`tests/scripts/test_deploy_build_inputs.py` documents as unarmed for the deploy filters.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any  # score:allow untyped any — parsed YAML documents

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-e2e.yml"
DEFAULT_COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

#: Compose flags that take a value, so the value is not mistaken for a service name.
_VALUE_FLAGS = {"-p", "--project-name", "--profile", "--env-file", "-f", "--file", "--scale"}

pytestmark = pytest.mark.unit

_COMPOSE_UP = re.compile(r"\bdocker(?:\s+compose|-compose)\b")
_BUILD = re.compile(r"\bdocker\s+build\b")
_DOCKERFILE_FLAG = re.compile(r"(?:^|\s)(?:-f|--file)[=\s]+(\S+)")
_SHELL_SPLIT = re.compile(r"&&|\|\||[;|\n]")
#: A trailing backslash continues the command onto the next line; the shell reads one
#: command, so the readers below must too. Left joined, the backslash becomes a token
#: and the real service names land in a segment nothing matches.
_CONTINUATION = re.compile(r"\\[ \t]*\n[ \t]*")


def _run_blocks() -> list[str]:
    """Every `run:` script in the workflow, however the step spells it."""
    parsed: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    blocks: list[str] = []
    for job in (parsed.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            script = step.get("run")
            if script:
                blocks.append(_CONTINUATION.sub(" ", str(script)))
    assert blocks, f"{WORKFLOW.name} has no runnable steps — did the workflow move?"
    return blocks


def _push_paths() -> list[str]:
    """The `on.push.paths` globs of the workflow.

    PyYAML resolves a bare top-level `on:` key to the boolean True (YAML 1.1), so the
    trigger block is not reachable under the string "on".
    """
    parsed: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    paths = list(parsed[True].get("push", {}).get("paths", []))
    assert paths, f"{WORKFLOW.name} has no `on.push.paths`; the filter moved or was dropped"
    return paths


def _compose_files() -> list[Path]:
    """The compose files the workflow's steps invoke (the default one when unnamed)."""
    found: list[Path] = []
    for block in _run_blocks():
        for segment in _SHELL_SPLIT.split(block):
            if not _COMPOSE_UP.search(segment) and not _BUILD.search(segment):
                continue
            flag = _DOCKERFILE_FLAG.search(segment) if _BUILD.search(segment) else None
            if flag:
                candidate = REPO_ROOT / flag.group(1)
                if candidate.suffix in {".yml", ".yaml"}:
                    found.append(candidate)
                    continue
            found.append(DEFAULT_COMPOSE_FILE)
    assert found, (
        f"{WORKFLOW.name} runs neither `docker compose` nor `docker build`; this guard "
        f"has nothing to derive from and would pass vacuously"
    )
    # `up`, `exec` and `down` all name the same file; walking its closure once per
    # invocation is wasted work and would multiply any failure message.
    return sorted(set(found))


def _compose_up_services() -> set[str]:
    """Service names given to a `docker compose … up` in the workflow."""
    services: set[str] = set()
    for block in _run_blocks():
        for segment in _SHELL_SPLIT.split(block):
            tokens = segment.split()
            if not _COMPOSE_UP.search(segment):
                continue
            try:
                start = tokens.index("up")
            except ValueError:
                continue
            rest = tokens[start + 1 :]
            skip_next = False
            for token in rest:
                if skip_next:
                    skip_next = False
                    continue
                if token in _VALUE_FLAGS:
                    skip_next = True
                    continue
                if token.startswith("-"):
                    continue
                services.add(token.strip("'\""))
    assert services, (
        f"{WORKFLOW.name} starts no compose service; the closure below would be empty and "
        f"every assertion would pass without proving anything"
    )
    return services


def _literal_build_dockerfiles() -> set[str]:
    """Repo-relative Dockerfiles built by a literal `docker build` step."""
    built: set[str] = set()
    for block in _run_blocks():
        for segment in _SHELL_SPLIT.split(block):
            if not _BUILD.search(segment):
                continue
            flag = _DOCKERFILE_FLAG.search(segment)
            path = flag.group(1) if flag else f"{segment.split()[-1].strip(chr(39))}/Dockerfile"
            built.add(path.removeprefix("./"))
    return built


def _services_by_name(compose_file: Path) -> dict[str, Any]:
    parsed: dict[Any, Any] = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = parsed.get("services") or {}
    assert services, f"{compose_file.name} declares no services — did it move?"
    return services


def _build_dockerfile(service: dict[str, Any]) -> str | None:
    """Repo-relative Dockerfile for a compose service, or None when it pulls an image.

    `build:` is either a bare path (the Docker Compose v2 short form) or a mapping.
    """
    build = service.get("build")
    if not build:
        return None
    if isinstance(build, str):
        return f"{build.removeprefix('./')}/Dockerfile"
    context = str(build.get("context", ".")).removeprefix("./")
    prefix = "" if context == "." else f"{context}/"
    # A mapping `build:` may omit `dockerfile:`; Compose then uses the context's
    # `Dockerfile`, which is the same default the short form above relies on.
    return f"{prefix}{build.get('dockerfile', 'Dockerfile')}"


def _built_dockerfiles(compose_file: Path, seeds: set[str]) -> set[str]:
    """Dockerfiles built by starting `seeds` and pulling their `depends_on` closure."""
    services = _services_by_name(compose_file)
    built: set[str] = set()
    seen: set[str] = set()
    pending = list(seeds)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        assert name in services, (
            f"{compose_file.name} has no service '{name}' — the workflow starts a "
            f"service this file does not define"
        )
        depends_on = services[name].get("depends_on") or {}
        pending.extend(depends_on if isinstance(depends_on, dict) else depends_on)
        dockerfile = _build_dockerfile(services[name])
        if dockerfile is not None:
            built.add(dockerfile)
    assert built, (
        f"nothing in the closure of {sorted(seeds)} has a `build:` section; nothing is "
        f"compiled by this job, so there is nothing to watch"
    )
    return built


def _glob_regex(glob: str) -> re.Pattern[str]:
    """Translate a git path glob to a regex over a repo-relative file path.

    `*` does not cross `/`, `**` does, and a leading `**/` may match zero directories the
    way git treats it — so `**/Dockerfile` covers a top-level `Dockerfile` too. Getting
    this wrong in the permissive direction makes the guard demand four explicit entries
    forever; getting it wrong in the strict direction lets an unwatched Dockerfile through,
    which is the bug this file exists for.
    """
    out = []
    # Longest alternative first, or `**/` and `**` get split into single `*`s.
    for part in re.split(r"(\*\*/|\*\*|\*)", glob):
        if part == "**/":
            out.append("(?:.*/)?")
        elif part == "**":
            out.append(".*")
        elif part == "*":
            out.append("[^/]*")
        else:
            out.append(re.escape(part))
    return re.compile("".join(out))


def _watched_by(dockerfile: str, globs: list[str]) -> bool:
    return any(re.fullmatch(_glob_regex(glob), dockerfile) for glob in globs)


def test_e2e_stack_job_is_triggered_by_every_dockerfile_it_builds() -> None:
    """The closure of the compose services this job starts, filtered.

    Derived from the workflow, so a service added to the `docker compose up` line — or a
    dependency added to one of those services — widens the closure and fails here until
    the filter widens with it.
    """
    globs = _push_paths()
    seeds = _compose_up_services()
    watched: set[str] = set()
    for compose_file in _compose_files():
        assert compose_file.is_file(), f"{compose_file} does not exist"
        watched |= _built_dockerfiles(compose_file, seeds)
    watched |= _literal_build_dockerfiles()

    missing = sorted(path for path in watched if not _watched_by(path, globs))
    assert not missing, (
        f"{WORKFLOW.name} does not watch {missing}, which the compose services it starts "
        f"build. Its `e2e` job is the only CI job that compiles those images, and it is "
        f"gated on `on.push.paths` — so an edit there merges with nothing having built "
        f"the image. Add each path to the filter (a '<dir>/Dockerfile' entry, or a "
        f"broader glob that matches it)."
    )


def test_the_closure_is_not_vacuous() -> None:
    """A guard that can pass by finding nothing is not a guard.

    Pins the two derivations this file rests on: the workflow really does start those four
    services through Compose, and every Dockerfile the derived closure names really exists
    on disk. If a Compose rewrite renames a service or moves a build context, this fails
    loudly instead of the filter test above quietly checking nothing.
    """
    seeds = _compose_up_services()
    assert {"digigraph", "digiquant", "digisearch", "digikey"} <= seeds, (
        f"the e2e job starts {sorted(seeds)}; the four services this file derives its "
        f"closure from are gone from the `docker compose up` line"
    )
    closure = _built_dockerfiles(DEFAULT_COMPOSE_FILE, seeds)
    for path in sorted(closure):
        assert (REPO_ROOT / path).is_file(), f"{path} does not exist on disk"
