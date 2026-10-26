"""DIG-2637: tenant-scoped skill documents, fetched by get_skill at call time.

Pinned properties:

1. The ``occ`` pack carries the four named skills; they load, and each carries a
   one-line description.
2. Skills are TENANT content. Another tenant lists none of them and cannot read
   one: the refusal for an outside id is the refusal for an unknown id. An
   unmapped tenant lists none, whatever is on disk.
3. get_skill returns the instructions; it is not a summary of them.
4. An unknown id is refused with a corrective message naming what does exist —
   and it names only this tenant's ids.
5. A skill id (and a pack name) is validated before it reaches the filesystem —
   no traversal, no absolute path, no nested name.
6. No document names a capability inventory. This is the DIG-100 / DIG-509 G1'
   rule as it applies to a prompt-bearing artefact: a source-or-refuse rule
   that also enumerates capabilities is the defect it exists to prevent. The
   absence test carries a firing positive control.
7. present-results carries the display rules the brief names.
8. Folder name and frontmatter name agree — one id per skill, no aliases.
9. A malformed folder raises; it never silently disappears from the pack.
10. The bundle is registered behind a ``when`` gate: a tenant with no skills
    gets no list_skills/get_skill tools at all.
11. The request-scoped allowlist still refuses these tools when it excludes
    them: research.py's union is the only lift and it is visible, not a hole.
12. research.py appends the bundle id only for a tenant that has a set, and
    unions the names only when the bundle is in play. This is a STRUCTURAL pin,
    not an execution of the research node: it reads the module source, so it
    dies when the wiring is deleted and it cannot see a wiring that is present
    but wrong. Property 11 covers the wrong case, from the other direction.
"""

from __future__ import annotations

import json
import re

import pytest

OCC = "occ"
HOUSE = "digithings-ai"

EXPECTED = (
    "find-precedent-tickets",
    "guide-help-docs",
    "present-results",
    "summarize-tickets-by-topic",
)


# leaf 1b of DIG-509 asserts exactly this absence on the canonical grounding
# text. The same rule, the same patterns, applied to the documents a
# client-visible agent is handed.
FORBIDDEN_IN_DOCUMENTS = (
    r"azure_ai_search",
    r"mcp",
    r"tool\s+(call|name|id)\b",
    r"\b(index|corpus|tenant)\b",
)


# A bare zammad tool name resolves to `Unknown tool`; only the prefixed form is
# callable. `zammad_` prefixed names must not be caught by these.
BARE_TOOL_NAMES = (
    "list_tickets",
    "aggregate_tickets",
    "ticket_report",
    "search_tickets",
    "get_ticket",
)


def _bare_tool_names_in(text):
    """Bare tool names in ``text``: not flanked by a word character.

    The negative lookarounds keep ``zammad_list_tickets`` out of the hits.
    """
    return [
        name
        for name in BARE_TOOL_NAMES
        if re.search(rf"(?<![_0-9A-Za-z]){name}(?![_0-9A-Za-z])", text)
    ]


def _docs(pack=OCC):
    from digigraph.skill_library import list_skill_documents

    return list_skill_documents(pack)


def _ctx(pack=OCC, ids=EXPECTED, **kw):
    from digigraph.orchestration.registry import ToolContext

    fields = {
        "session_id": None,
        "run_data_dir": None,
        "index_name": "default",
        "index_config": {},
        "state": {},
        "skill_pack": pack,
        "skill_ids": frozenset(ids),
    }
    fields.update(kw)
    return ToolContext(**fields)


def _handler():
    from digigraph.skill_library.tools import skill_library_tool_handler

    return skill_library_tool_handler("get_skill")


def _make_library(tmp_path, monkeypatch, packs):
    """Point the loader at a two-tenant library: ``{pack: {name: description}}``.

    Each document is a real SKILL.md, so the loader's own frontmatter rules run.
    """
    from digigraph.skill_library import loader

    for pack, skills in packs.items():
        for name, description in skills.items():
            folder = tmp_path / pack / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {description}\n---\n{name} instructions\n",
                encoding="utf-8",
            )
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", tmp_path)
    return tmp_path


@pytest.mark.unit
def test_the_occ_pack_carries_the_four_documents():
    docs = _docs(OCC)
    assert tuple(d.name for d in docs) == EXPECTED, [d.name for d in docs]
    for doc in docs:
        assert doc.description.strip(), doc.name
        assert "\n" not in doc.description, f"{doc.name}: description must be one line"
        assert doc.body.strip(), doc.name
        assert doc.source.endswith(f"{doc.name}/SKILL.md"), doc.source
        assert doc.source.startswith(f"skill_library/{OCC}/"), doc.source


@pytest.mark.unit
def test_get_skill_returns_the_instructions_not_a_summary():
    result = _handler()({"name": "present-results"}, _ctx())
    assert result["ok"] is True, result
    assert result["name"] == "present-results"
    assert result["content"] != result["description"]
    assert "Cite ids" in result["content"]
    assert result["version"] == "1"


@pytest.mark.unit
def test_get_skill_refuses_an_unknown_id_and_names_only_this_tenants_ids():
    handler = _handler()
    result = handler({"name": "no-such-skill"}, _ctx())
    assert result["ok"] is False, result
    assert "unknown skill" in result["error"]
    assert tuple(result["known_skills"]) == EXPECTED
    # A missing argument is the same refusal, not a traceback.
    assert handler({}, _ctx())["ok"] is False


@pytest.mark.unit
def test_another_tenant_lists_none_and_cannot_read_an_occ_skill():
    """The house chat must not receive the OCC workflows, in either direction."""
    from digigraph.skill_library.tools import skill_library_tool_handler

    house = _ctx(pack=HOUSE, ids=())

    listed = skill_library_tool_handler("list_skills")({}, house)
    assert listed["ok"] is True, listed
    assert listed["count"] == 0
    assert listed["skills"] == []

    handler = _handler()
    for occ_id in EXPECTED:
        outside = handler({"name": occ_id}, house)
        unknown = handler({"name": "no-such-skill"}, house)
        assert outside["ok"] is False, outside
        assert "content" not in outside
        # Same refusal as an unknown id: not a hint that the id exists elsewhere.
        assert outside["error"] == f"unknown skill: {occ_id}"
        assert outside["known_skills"] == unknown["known_skills"] == []
        assert outside["error"].split(": ")[0] == unknown["error"].split(": ")[0]


@pytest.mark.unit
def test_one_tenant_cannot_read_another_tenants_document(tmp_path, monkeypatch):
    _make_library(
        tmp_path,
        monkeypatch,
        {OCC: {"present-results": "occ only"}, HOUSE: {"house-report": "house only"}},
    )
    handler = _handler()
    house = _ctx(pack=HOUSE, ids=("house-report",))
    assert handler({"name": "house-report"}, house)["ok"] is True
    outside = handler({"name": "present-results"}, house)
    assert outside["ok"] is False, outside
    assert "content" not in outside
    assert outside["known_skills"] == ["house-report"]
    # And the other way round: the occ context does not see the house document.
    occ = _ctx(pack=OCC, ids=("present-results",))
    assert handler({"name": "house-report"}, occ)["ok"] is False


@pytest.mark.unit
def test_the_tenant_map_decides_the_set_and_unmapped_means_none(tmp_path, monkeypatch):
    """The filesystem is where the text lives; the map is the grant."""
    from digigraph.corpus_routing import load_tenant_corpus_map, tenant_skill_ids

    _make_library(
        tmp_path,
        monkeypatch,
        {
            OCC: {name: f"{name} doc" for name in EXPECTED},
            # Present on disk on purpose: being on disk must not be enough for a
            # tenant the map does not carry.
            "stranger": {"present-results": "not yours"},
        },
    )
    table = load_tenant_corpus_map(
        json.dumps(
            {
                OCC: {"digisearchIndex": "tenant-help"},
                HOUSE: {"digisearchIndex": "house-docs"},
            }
        )
    )
    # The occ entry names no skills, so its own pack is the set.
    assert tenant_skill_ids(OCC, table) == EXPECTED
    # A mapped tenant with no pack directory of its own gets nothing.
    assert tenant_skill_ids(HOUSE, table) == ()
    # An unmapped tenant gets nothing even though a directory carries its slug.
    assert tenant_skill_ids("stranger", table) == ()
    # No map at all (single-tenant): no skills, never "all".
    assert tenant_skill_ids(OCC, {}) == ()
    assert tenant_skill_ids(None, table) == ()


@pytest.mark.unit
def test_an_explicit_skills_list_narrows_the_pack(tmp_path, monkeypatch):
    from digigraph.corpus_routing import load_tenant_corpus_map, tenant_skill_ids
    from digigraph.skill_library.tools import skill_library_tool_handler

    _make_library(
        tmp_path,
        monkeypatch,
        {OCC: {name: f"{name} doc" for name in EXPECTED}},
    )
    table = load_tenant_corpus_map(json.dumps({OCC: {"skills": ["present-results"]}}))
    assert tenant_skill_ids(OCC, table) == ("present-results",)
    listed = skill_library_tool_handler("list_skills")({}, _ctx(ids=tenant_skill_ids(OCC, table)))
    assert [s["name"] for s in listed["skills"]] == ["present-results"]
    # An explicit empty list is "no skills", not "fall back to the pack".
    table = load_tenant_corpus_map(json.dumps({OCC: {"skills": []}}))
    assert tenant_skill_ids(OCC, table) == ()


@pytest.mark.unit
def test_a_skill_id_is_validated_before_it_reaches_the_filesystem():
    from digigraph.skill_library import loader

    handler = _handler()
    escapes = [
        "../loader",
        "../../etc/passwd",
        "/etc/passwd",
        "occ/present-results",
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
    # The loader refuses the same ids directly, before any filesystem join.
    for candidate in ("../loader", "/etc/passwd", "occ/present-results", "present results"):
        with pytest.raises(loader.SkillDocumentError, match="not a valid skill id"):
            loader.load_skill_document(candidate, OCC)
    # A pack name is joined to the library root too, so it is validated the same
    # way: no traversal out of skill_library, no absolute path, no parent dir.
    for pack in ("../occ", "/etc", "occ/../occ", "o cc"):
        assert loader.pack_dir(pack) is None, pack
        assert loader.list_skill_documents(pack) == [], pack
        with pytest.raises(loader.SkillDocumentError, match="unknown skill"):
            loader.load_skill_document("present-results", pack)
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
def test_every_skill_translates_non_chat_language_terms():
    """DIG-3355 (d): the same translation rule is in every skill."""
    from digigraph.skill_library import load_skill_document

    for name in EXPECTED:
        body = load_skill_document(name, OCC).body
        assert 'in progress ("in Bearbeitung")' in body, name
        assert "already in the chat language" in body, name


@pytest.mark.unit
def test_precedent_skill_cites_resolved_tickets():
    from digigraph.skill_library import load_skill_document

    body = load_skill_document("find-precedent-tickets", OCC).body
    assert "`zammad_search_tickets`" in body
    assert "Advise the fix first" in body
    assert "`zammad_get_ticket`" in body
    assert "digisearch_zammad_tickets" not in body
    assert "digisearch_occ_help" not in body
    assert _bare_tool_names_in(body) == []


@pytest.mark.unit
def test_topical_skill_keeps_counts_off_keyword_search():
    """DIG-3355 (b): keyword search explores; counts come from Zammad metadata tools."""
    from digigraph.skill_library import load_skill_document

    body = " ".join(load_skill_document("summarize-tickets-by-topic", OCC).body.split())
    assert "Keyword search (`zammad_search_tickets`) is for exploration: finding" in body
    assert "Counts and precise metrics must come from the Zammad metadata" in body
    assert "`zammad_aggregate_tickets`" in body
    assert "`zammad_ticket_report`" in body
    assert "`zammad_list_tickets`" in body
    assert "Never report a count taken from search hits." in body
    assert "digisearch_zammad_tickets" not in body
    assert _bare_tool_names_in(body) == []


@pytest.mark.unit
def test_ticket_skills_name_only_the_prefixed_tool_forms():
    """A bare zammad name is `Unknown tool`; the three skills must use the prefix."""
    from digigraph.skill_library import load_skill_document

    # Positive control: the matcher fires on bare names, so a zero below is a
    # pass and not a matcher that matches nothing.
    assert _bare_tool_names_in("use `list_tickets` and `get_ticket`") == [
        "list_tickets",
        "get_ticket",
    ]
    # Positive control the other way: the prefixed forms are not bare names.
    assert _bare_tool_names_in("call `zammad_list_tickets` then `zammad_get_ticket`") == []

    for name in (
        "find-precedent-tickets",
        "summarize-tickets-by-topic",
        "guide-help-docs",
    ):
        body = load_skill_document(name, OCC).body
        hits = _bare_tool_names_in(body)
        assert hits == [], f"{name} names a bare tool: {hits}"
        assert "`zammad_search_tickets`" in body, name
        assert "digisearch_zammad_tickets" not in body, name
        assert "digisearch_occ_help" not in body, name


@pytest.mark.unit
def test_help_docs_skill_carries_the_manual_map():
    from digigraph.skill_library import load_skill_document

    body = load_skill_document("guide-help-docs", OCC).body
    assert "digisearch_occ_help" not in body
    assert "digisearch_zammad_tickets" not in body
    for required in (
        "`digisearch`",
        "`zammad_search_tickets`",
        "Cloud Portal manual",
        "OCC Search manual",
        "6 Backup and Restore",
        "12 Legal holds",
        "not available",
        "E-learning videos are out of scope",
    ):
        assert required in body, required


@pytest.mark.unit
def test_present_results_carries_the_display_rules_the_brief_names():
    from digigraph.skill_library import load_skill_document

    body = load_skill_document("present-results", OCC).body
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
    (tmp_path / OCC / "good").mkdir(parents=True)
    (tmp_path / OCC / "good" / "SKILL.md").write_text(
        "---\nname: good\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    (tmp_path / OCC / "aliased").mkdir()
    (tmp_path / OCC / "aliased" / "SKILL.md").write_text(
        "---\nname: somethingelse\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", tmp_path)
    # The alias is a packaging fault, so it raises rather than being skipped.
    with pytest.raises(loader.SkillDocumentError, match="does not match its folder"):
        loader.list_skill_documents(OCC)
    with pytest.raises(loader.SkillDocumentError, match="does not match its folder"):
        loader.load_skill_document("aliased", OCC)
    # Positive control: the well-formed folder is served from the same pack.
    assert loader.load_skill_document("good", OCC).name == "good"
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", real)
    assert loader.known_skill_names(OCC) == list(EXPECTED)
    # And the library root itself is not a pack: no unscoped listing.
    assert loader.known_skill_names() == []


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

    (tmp_path / OCC / folder).mkdir(parents=True)
    (tmp_path / OCC / folder / "SKILL.md").write_text(contents, encoding="utf-8")
    (tmp_path / OCC / "not-a-skill").mkdir()  # no SKILL.md: not a skill, not an error
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", tmp_path)
    with pytest.raises(loader.SkillDocumentError, match=expected):
        loader.list_skill_documents(OCC)
    # Positive control: undo restores the real library, so the raise above was
    # the document and not an empty or unreadable pack.
    monkeypatch.undo()
    assert loader.known_skill_names(OCC) == list(EXPECTED)


@pytest.mark.unit
def test_the_bundle_is_gated_on_the_tenant_having_skills():
    from digigraph.orchestration import builtin  # noqa: F401 - registers tools + skills
    from digigraph.orchestration.registry import execute, get_tools, has_tool
    from digigraph.skill_library.tools import SKILL_LIBRARY_SKILL_ID, SKILL_LIBRARY_TOOL_NAMES

    assert SKILL_LIBRARY_SKILL_ID == "skill_library"
    assert SKILL_LIBRARY_TOOL_NAMES == {"list_skills", "get_skill"}
    for name in SKILL_LIBRARY_TOOL_NAMES:
        assert has_tool(name), name

    # A tenant with skills gets both tools.
    tools = get_tools([SKILL_LIBRARY_SKILL_ID], _ctx(session_id="s"))
    names = {t["function"]["name"] for t in tools}
    assert names == SKILL_LIBRARY_TOOL_NAMES, names

    served = execute("get_skill", {"name": "summarize-tickets-by-topic"}, _ctx(session_id="s"))
    assert served["ok"] is True, served
    assert served["name"] == "summarize-tickets-by-topic"

    # A tenant with none gets neither — the tools do not exist for it, and the
    # handler behind them still refuses every id if something calls it anyway.
    none = _ctx(session_id="s", pack=None, ids=())
    assert get_tools([SKILL_LIBRARY_SKILL_ID], none) == []
    refused = execute("get_skill", {"name": "present-results"}, none)
    assert refused["ok"] is False, refused
    assert "content" not in refused


@pytest.mark.unit
def test_a_request_scoped_allowlist_still_refuses_these_tools():
    from digigraph.orchestration import builtin  # noqa: F401 - registers the tools
    from digigraph.orchestration.registry import execute

    # research.py unions the two names into _allowed_names before it builds the
    # context. That union is the only lift: a context that excludes them must
    # still refuse, or the bundle would be a hole in the allowlist.
    refused = execute(
        "get_skill",
        {"name": "present-results"},
        _ctx(session_id="s", allowed_tool_names=frozenset({"digisearch"})),
    )
    assert refused.get("error") == "tool_not_allowed", refused


@pytest.mark.unit
def test_the_map_reaches_the_request_and_the_graph_state(monkeypatch):
    """The map -> override -> request -> graph-state hops all exist (DIG-4459).

    A resolved set that stops at the context is a silent no-skill: research.py
    reads ``state["skills"]``, so the carrier has to reach the state.
    """
    from types import SimpleNamespace

    from digigraph.http_api.context import _digi_fields_from_request
    from digigraph.models import WorkflowRequest
    from digigraph.workflow import _initial_graph_state

    monkeypatch.setenv(
        "DIGI_TENANT_CORPUS_MAP",
        json.dumps(
            {
                OCC: {"digisearchIndex": "tenant-help"},
                "house": {"digisearchIndex": "house-docs"},
            }
        ),
    )

    def _request(slug):
        return SimpleNamespace(
            state=SimpleNamespace(
                digi_bearer=None,
                digi_auth=SimpleNamespace(
                    subject="",
                    key_prefix=None,
                    tenant_slug=slug,
                    project_id=None,
                    jti=None,
                ),
            ),
            headers={},
        )

    updates = _digi_fields_from_request(_request(OCC))
    assert updates["skill_pack"] == OCC
    assert tuple(updates["skills"]) == EXPECTED
    request = WorkflowRequest(prompt="hi", **{k: v for k, v in updates.items() if v is not None})
    state = _initial_graph_state(request, "wf-skills")
    assert state["skill_pack"] == OCC
    assert tuple(state["skills"]) == EXPECTED

    # A mapped tenant with no pack of its own: both keys are written, and they
    # are empty — a prior turn's set cannot survive on the same thread.
    house = _digi_fields_from_request(_request("house"))
    assert house["skill_pack"] is None
    assert house["skills"] == []


@pytest.mark.unit
def test_research_appends_the_bundle_only_for_a_tenant_with_skills():
    import inspect

    from digigraph.graph import research

    source = inspect.getsource(research)
    # Assert the GUARDED form. An earlier version of this pin asserted only the
    # append, and a mutant that replaced the guard with `if False:` still left
    # the append in the source — so the pin was satisfied by dead code. The
    # guard is now the tenant's set, so a tenant without skills never reaches
    # the append.
    assert (
        "if _tenant_skill_ids and _tenant_skill_pack and SKILL_LIBRARY_SKILL_ID not in skill_ids:\n"
        "        skill_ids.append(SKILL_LIBRARY_SKILL_ID)" in source
    ), "bundle id is not appended behind the tenant-skills guard"
    assert "_allowed_names | SKILL_LIBRARY_TOOL_NAMES" in source, (
        "the bundle names are not unioned into a request-scoped allowlist"
    )
    assert "if SKILL_LIBRARY_SKILL_ID in skill_ids:" in source, (
        "the allowlist lift is not gated on the bundle being in play"
    )
