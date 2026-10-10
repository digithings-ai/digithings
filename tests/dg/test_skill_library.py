"""DIG-2637: skill documents for digigraph, fetched by get_skill at call time.

Pinned properties:

1. The three named skills exist, load, and carry a one-line description.
2. get_skill returns the instructions; it is not a summary of them.
3. An unknown id is refused with a corrective message naming what does exist.
4. A skill id is validated before it reaches the filesystem — no traversal.
5. No document names a capability inventory. This is the DIG-100 / DIG-509 G1'
   rule as it applies to a prompt-bearing artefact: a source-or-refuse rule
   that also enumerates capabilities is the defect it exists to prevent. The
   absence test carries a firing positive control.
6. present-results carries the display rules the brief names.
7. Folder name and frontmatter name agree — one id per skill, no aliases.
8. A malformed folder raises; it never silently disappears from the library.
9. The bundle is registered always-on, like session.
10. The request-scoped allowlist still refuses these tools when it excludes
    them: research.py's union is the only lift and it is visible, not a hole.
11. research.py actually appends the bundle id and unions the two names.
    This is a STRUCTURAL pin, not an execution of the research node: it reads
    the module source, so it dies when the wiring is deleted and it cannot see
    a wiring that is present but wrong. Property 10 covers the wrong case, from
    the other direction.
"""

from __future__ import annotations

import re

import pytest

EXPECTED = ("find-precedent-tickets", "present-results", "summarize-tickets-by-topic")


# leaf 1b of DIG-509 asserts exactly this absence on the canonical grounding
# text. The same rule, the same patterns, applied to the documents a
# client-visible agent is handed.
FORBIDDEN_IN_DOCUMENTS = (
    r"azure_ai_search",
    r"mcp",
    r"tool\s+(call|name|id)\b",
    r"\b(index|corpus|tenant)\b",
)


def _docs():
    from digigraph.skill_library import list_skill_documents

    return list_skill_documents()


def _ctx(**kw):
    from digigraph.orchestration.registry import ToolContext

    fields = {
        "session_id": None,
        "run_data_dir": None,
        "index_name": "default",
        "index_config": {},
        "state": {},
    }
    fields.update(kw)
    return ToolContext(**fields)


@pytest.mark.unit
def test_the_three_named_skills_are_present_and_readable():
    docs = _docs()
    assert tuple(d.name for d in docs) == EXPECTED, [d.name for d in docs]
    for doc in docs:
        assert doc.description.strip(), doc.name
        assert "\n" not in doc.description, f"{doc.name}: description must be one line"
        assert doc.body.strip(), doc.name
        assert doc.source.endswith(f"{doc.name}/SKILL.md"), doc.source


@pytest.mark.unit
def test_get_skill_returns_the_instructions_not_a_summary():
    from digigraph.skill_library.tools import skill_library_tool_handler

    result = skill_library_tool_handler("get_skill")({"name": "present-results"}, _ctx())
    assert result["ok"] is True, result
    assert result["name"] == "present-results"
    assert result["content"] != result["description"]
    assert "Cite ids" in result["content"]
    assert result["version"] == "1"


@pytest.mark.unit
def test_get_skill_refuses_an_unknown_id_and_names_what_exists():
    from digigraph.skill_library.tools import skill_library_tool_handler

    handler = skill_library_tool_handler("get_skill")
    result = handler({"name": "no-such-skill"}, _ctx())
    assert result["ok"] is False, result
    assert "unknown skill" in result["error"]
    assert tuple(result["known_skills"]) == EXPECTED
    # A missing argument is the same refusal, not a traceback.
    assert handler({}, _ctx())["ok"] is False


@pytest.mark.unit
def test_a_skill_id_is_validated_before_it_reaches_the_filesystem():
    from digigraph.skill_library.tools import skill_library_tool_handler

    handler = skill_library_tool_handler("get_skill")
    escapes = [
        "../loader",
        "../../etc/passwd",
        "/etc/passwd",
        "present-results/../../digigraph/orchestration/registry",
        "present results",
        "Present-Results",
        "",
        "present-results\n",
    ]
    for candidate in escapes:
        result = handler({"name": candidate}, _ctx())
        assert result["ok"] is False, f"{candidate!r} was served: {result}"
        assert "content" not in result, candidate
    # Positive control: the same handler serves the real id, so the loop above
    # is testing the id check and not a handler that refuses everything.
    assert handler({"name": "present-results"}, _ctx())["ok"] is True


@pytest.mark.unit
def test_no_document_names_a_capability_inventory():
    # Positive control first: the patterns must be able to fire, or the zero
    # below is a pattern that never matches anything.
    probe = (
        "Call azure_ai_search then the mcp server; report the tool name and tool id. "
        "The index and corpus are per-tenant."
    )
    fired = [p for p in FORBIDDEN_IN_DOCUMENTS if re.search(p, probe, re.IGNORECASE)]
    assert len(fired) == len(FORBIDDEN_IN_DOCUMENTS), f"control did not fire: {fired}"

    for doc in _docs():
        text = f"{doc.description}\n{doc.body}"
        for pattern in FORBIDDEN_IN_DOCUMENTS:
            hit = re.search(pattern, text, re.IGNORECASE)
            assert hit is None, f"{doc.name} names a capability ({pattern!r}): {hit.group(0)!r}"


@pytest.mark.unit
def test_present_results_carries_the_display_rules_the_brief_names():
    from digigraph.skill_library import load_skill_document

    body = load_skill_document("present-results").body
    for required in (
        "Never leak",
        "Never quote",
        "Cite ids",
        "**Table**",
        "**Summary**",
    ):
        assert required in body, required


@pytest.mark.unit
def test_folder_name_and_frontmatter_name_agree(tmp_path, monkeypatch):
    from digigraph.skill_library import loader

    real = loader.SKILL_LIBRARY_DIR
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "SKILL.md").write_text(
        "---\nname: good\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    (tmp_path / "aliased").mkdir()
    (tmp_path / "aliased" / "SKILL.md").write_text(
        "---\nname: somethingelse\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", tmp_path)
    # The alias is a packaging fault, so it raises rather than being skipped.
    with pytest.raises(loader.SkillDocumentError, match="does not match its folder"):
        loader.list_skill_documents()
    with pytest.raises(loader.SkillDocumentError, match="does not match its folder"):
        loader.load_skill_document("aliased")
    # Positive control: the well-formed folder is served from the same library.
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", real)
    assert loader.known_skill_names() == list(EXPECTED)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("folder", "contents", "expected"),
    [
        ("plain", "just prose\n", "no YAML frontmatter"),
        ("nod-desc", "---\nname: nod-desc\n---\nbody\n", "frontmatter missing description"),
        ("nod-name", "---\ndescription: d\n---\nbody\n", "frontmatter missing name"),
        (
            "Not-Kebab",
            "---\nname: Not-Kebab\ndescription: d\n---\nbody\n",
            "not kebab-case",
        ),
        ("empty", "---\nname: empty\ndescription: d\n---\n\n", "no instructions"),
        (
            "unclosed",
            '---\nname: "unterminated\ndescription: d\n---\nbody\n',
            "not valid YAML",
        ),
        ("seq", "---\n- name: seq\n- description: d\n---\nbody\n", "must be a mapping"),
    ],
)
def test_a_malformed_folder_raises_rather_than_disappearing(
    tmp_path, monkeypatch, folder, contents, expected
):
    from digigraph.skill_library import loader

    (tmp_path / folder).mkdir()
    (tmp_path / folder / "SKILL.md").write_text(contents, encoding="utf-8")
    (tmp_path / "not-a-skill").mkdir()  # no SKILL.md: not a skill at all, not an error
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", tmp_path)
    with pytest.raises(loader.SkillDocumentError, match=expected):
        loader.list_skill_documents()
    # Positive control: undo restores the real library, so the raise above was
    # the document and not an empty or unreadable library.
    monkeypatch.undo()
    assert loader.known_skill_names() == list(EXPECTED)


@pytest.mark.unit
def test_the_bundle_is_registered_always_on_like_session():
    from digigraph.orchestration import builtin  # noqa: F401 - registers tools + skills
    from digigraph.orchestration.registry import execute, get_tools, has_tool
    from digigraph.skill_library.tools import SKILL_LIBRARY_SKILL_ID, SKILL_LIBRARY_TOOL_NAMES

    assert SKILL_LIBRARY_SKILL_ID == "skill_library"
    assert SKILL_LIBRARY_TOOL_NAMES == {"list_skills", "get_skill"}
    for name in SKILL_LIBRARY_TOOL_NAMES:
        assert has_tool(name), name

    tools = get_tools([SKILL_LIBRARY_SKILL_ID], _ctx(session_id="s"))
    names = {t["function"]["name"] for t in tools}
    assert names == SKILL_LIBRARY_TOOL_NAMES, names

    served = execute("get_skill", {"name": "summarize-tickets-by-topic"}, _ctx(session_id="s"))
    assert served["ok"] is True, served
    assert served["name"] == "summarize-tickets-by-topic"


@pytest.mark.unit
def test_a_request_scoped_allowlist_still_refuses_these_tools():
    from digigraph.orchestration import builtin  # noqa: F401 - registers the tools
    from digigraph.orchestration.registry import execute

    # research.py unions the two names into _allowed_names before it builds the
    # context. That union is the only lift: a context that excludes them must
    # still refuse, or the always-on bundle would be a hole in the allowlist.
    refused = execute(
        "get_skill",
        {"name": "present-results"},
        _ctx(session_id="s", allowed_tool_names=frozenset({"digisearch"})),
    )
    assert refused.get("error") == "tool_not_allowed", refused


@pytest.mark.unit
def test_research_appends_the_bundle_and_unions_the_names():
    import inspect

    from digigraph.graph import research

    source = inspect.getsource(research)
    assert "skill_ids.append(SKILL_LIBRARY_SKILL_ID)" in source, "bundle id not appended"
    assert "_allowed_names | SESSION_TOOL_NAMES | SKILL_LIBRARY_TOOL_NAMES" in source, (
        "the always-on names are not unioned into a request-scoped allowlist"
    )
