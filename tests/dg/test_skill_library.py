"""DIG-2637: tenant-scoped skill documents, fetched by get_skill at call time.

These tests run on a fixture library (``acme`` is an example tenant), so they
pin the loader, the tenant grant and the tool wiring without depending on any
real tenant's documents. A deployment's own pack carries its own content tests.

Pinned properties:

1. A pack lists its documents; each carries a one-line description.
2. Skills are TENANT content. Another tenant lists none of them and cannot read
   one: the refusal for an outside id is the refusal for an unknown id. An
   unmapped tenant lists none, whatever is on disk.
3. get_skill returns the instructions; it is not a summary of them.
4. An unknown id is refused with a corrective message naming only this
   tenant's ids.
5. A skill id (and a pack name) is validated before it reaches the filesystem.
6. Folder name and frontmatter name agree; a malformed folder raises.
7. The bundle is registered behind a ``when`` gate: a tenant with no skills
   gets no list_skills/get_skill tools at all.
8. The request-scoped allowlist still refuses these tools when it excludes them.
9. research.py appends the bundle id only for a tenant that has a set
   (structural pin of the guarded form).
"""

from __future__ import annotations

import json

import pytest

TENANT = "acme"
HOUSE = "digithings-ai"

EXPECTED = (
    "find-precedents",
    "guide-help-docs",
    "present-results",
)


def _write(folder, name, description, body):
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: {description}\nversion: "1"\n---\n{body}\n',
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def library(tmp_path, monkeypatch):
    """The fixture library: one ``acme`` pack carrying ``EXPECTED``."""
    from digigraph.skill_library import loader

    root = tmp_path / "skill_library"
    for name in EXPECTED:
        _write(root / TENANT / name, name, f"{name} summary", f"{name} instructions. Cite ids.")
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", root)
    return root


def _ctx(pack=TENANT, ids=EXPECTED, **kw):
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


@pytest.mark.unit
def test_a_pack_lists_its_documents():
    from digigraph.skill_library import list_skill_documents

    docs = list_skill_documents(TENANT)
    assert tuple(d.name for d in docs) == EXPECTED, [d.name for d in docs]
    for doc in docs:
        assert doc.description.strip(), doc.name
        assert "\n" not in doc.description, f"{doc.name}: description must be one line"
        assert doc.body.strip(), doc.name
        assert doc.source.endswith(f"{doc.name}/SKILL.md"), doc.source
        assert doc.source.startswith(f"skill_library/{TENANT}/"), doc.source


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
    assert handler({}, _ctx())["ok"] is False


@pytest.mark.unit
def test_another_tenant_lists_none_and_cannot_read_a_tenant_skill():
    from digigraph.skill_library.tools import skill_library_tool_handler

    house = _ctx(pack=HOUSE, ids=())
    listed = skill_library_tool_handler("list_skills")({}, house)
    assert listed["ok"] is True, listed
    assert listed["count"] == 0
    assert listed["skills"] == []

    handler = _handler()
    for skill_id in EXPECTED:
        outside = handler({"name": skill_id}, house)
        unknown = handler({"name": "no-such-skill"}, house)
        assert outside["ok"] is False, outside
        assert "content" not in outside
        assert outside["error"] == f"unknown skill: {skill_id}"
        assert outside["known_skills"] == unknown["known_skills"] == []


@pytest.mark.unit
def test_one_tenant_cannot_read_another_tenants_document(library):
    _write(library / HOUSE / "house-report", "house-report", "house only", "house body")
    handler = _handler()
    house = _ctx(pack=HOUSE, ids=("house-report",))
    assert handler({"name": "house-report"}, house)["ok"] is True
    outside = handler({"name": "present-results"}, house)
    assert outside["ok"] is False, outside
    assert "content" not in outside
    assert outside["known_skills"] == ["house-report"]
    tenant = _ctx(pack=TENANT, ids=("present-results",))
    assert handler({"name": "house-report"}, tenant)["ok"] is False


@pytest.mark.unit
def test_the_tenant_map_decides_the_set_and_unmapped_means_none(library):
    from digigraph.corpus_routing import load_tenant_corpus_map, tenant_skill_ids

    # On disk on purpose: being on disk is not enough for an unmapped tenant.
    _write(library / "stranger" / "present-results", "present-results", "not yours", "x")
    table = load_tenant_corpus_map(
        json.dumps(
            {
                TENANT: {"digisearchIndex": "tenant-help"},
                HOUSE: {"digisearchIndex": "house-docs"},
            }
        )
    )
    assert tenant_skill_ids(TENANT, table) == EXPECTED
    assert tenant_skill_ids(HOUSE, table) == ()
    assert tenant_skill_ids("stranger", table) == ()
    assert tenant_skill_ids(TENANT, {}) == ()
    assert tenant_skill_ids(None, table) == ()


@pytest.mark.unit
def test_an_explicit_skills_list_narrows_the_pack():
    from digigraph.corpus_routing import load_tenant_corpus_map, tenant_skill_ids
    from digigraph.skill_library.tools import skill_library_tool_handler

    table = load_tenant_corpus_map(json.dumps({TENANT: {"skills": ["present-results"]}}))
    assert tenant_skill_ids(TENANT, table) == ("present-results",)
    listed = skill_library_tool_handler("list_skills")(
        {}, _ctx(ids=tenant_skill_ids(TENANT, table))
    )
    assert [s["name"] for s in listed["skills"]] == ["present-results"]
    table = load_tenant_corpus_map(json.dumps({TENANT: {"skills": []}}))
    assert tenant_skill_ids(TENANT, table) == ()


@pytest.mark.unit
def test_a_skill_id_is_validated_before_it_reaches_the_filesystem():
    from digigraph.skill_library import loader

    handler = _handler()
    escapes = [
        "../loader",
        "../../etc/passwd",
        "/etc/passwd",
        f"{TENANT}/present-results",
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
    for candidate in ("../loader", "/etc/passwd", f"{TENANT}/present-results", "present results"):
        with pytest.raises(loader.SkillDocumentError, match="not a valid skill id"):
            loader.load_skill_document(candidate, TENANT)
    for pack in (f"../{TENANT}", "/etc", f"{TENANT}/../{TENANT}", "a cme"):
        assert loader.pack_dir(pack) is None, pack
        assert loader.list_skill_documents(pack) == [], pack
        with pytest.raises(loader.SkillDocumentError, match="unknown skill"):
            loader.load_skill_document("present-results", pack)
    # Positive control: the same handler serves the real id.
    assert handler({"name": "present-results"}, _ctx())["ok"] is True


@pytest.mark.unit
def test_folder_name_and_frontmatter_name_agree(library):
    from digigraph.skill_library import loader

    _write(library / TENANT / "aliased", "somethingelse", "d", "body")
    with pytest.raises(loader.SkillDocumentError, match="does not match its folder"):
        loader.list_skill_documents(TENANT)
    with pytest.raises(loader.SkillDocumentError, match="does not match its folder"):
        loader.load_skill_document("aliased", TENANT)
    assert loader.load_skill_document("present-results", TENANT).name == "present-results"
    # The library root itself is not a pack: no unscoped listing.
    assert loader.known_skill_names() == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("folder", "contents", "expected"),
    [
        ("plain", "just prose\n", "no YAML frontmatter"),
        ("nod-desc", "---\nname: nod-desc\n---\nbody\n", "frontmatter missing description"),
        ("nod-name", "---\ndescription: d\n---\nbody\n", "frontmatter missing name"),
        ("Not-Kebab", "---\nname: Not-Kebab\ndescription: d\n---\nbody\n", "not kebab-case"),
        ("empty", "---\nname: empty\ndescription: d\n---\n\n", "no instructions"),
        ("unclosed", '---\nname: "unterminated\ndescription: d\n---\nbody\n', "not valid YAML"),
        ("seq", "---\n- name: seq\n- description: d\n---\nbody\n", "must be a mapping"),
    ],
)
def test_a_malformed_folder_raises_rather_than_disappearing(library, folder, contents, expected):
    from digigraph.skill_library import loader

    assert loader.known_skill_names(TENANT) == list(EXPECTED)  # positive control
    (library / TENANT / folder).mkdir()
    (library / TENANT / folder / "SKILL.md").write_text(contents, encoding="utf-8")
    (library / TENANT / "not-a-skill").mkdir()  # no SKILL.md: not a skill, not an error
    with pytest.raises(loader.SkillDocumentError, match=expected):
        loader.list_skill_documents(TENANT)


@pytest.mark.unit
def test_the_bundle_is_gated_on_the_tenant_having_skills():
    from digigraph.orchestration import builtin  # noqa: F401 - registers tools + skills
    from digigraph.orchestration.registry import execute, get_tools, has_tool
    from digigraph.skill_library.tools import SKILL_LIBRARY_SKILL_ID, SKILL_LIBRARY_TOOL_NAMES

    assert SKILL_LIBRARY_SKILL_ID == "skill_library"
    assert SKILL_LIBRARY_TOOL_NAMES == {"list_skills", "get_skill"}
    for name in SKILL_LIBRARY_TOOL_NAMES:
        assert has_tool(name), name

    tools = get_tools([SKILL_LIBRARY_SKILL_ID], _ctx(session_id="s"))
    assert {t["function"]["name"] for t in tools} == SKILL_LIBRARY_TOOL_NAMES

    served = execute("get_skill", {"name": "guide-help-docs"}, _ctx(session_id="s"))
    assert served["ok"] is True, served
    assert served["name"] == "guide-help-docs"

    none = _ctx(session_id="s", pack=None, ids=())
    assert get_tools([SKILL_LIBRARY_SKILL_ID], none) == []
    refused = execute("get_skill", {"name": "present-results"}, none)
    assert refused["ok"] is False, refused
    assert "content" not in refused


@pytest.mark.unit
def test_a_request_scoped_allowlist_still_refuses_these_tools():
    from digigraph.orchestration import builtin  # noqa: F401 - registers the tools
    from digigraph.orchestration.registry import execute

    refused = execute(
        "get_skill",
        {"name": "present-results"},
        _ctx(session_id="s", allowed_tool_names=frozenset({"digisearch"})),
    )
    assert refused.get("error") == "tool_not_allowed", refused


@pytest.mark.unit
def test_the_map_reaches_the_request_and_the_graph_state(monkeypatch):
    """The map -> override -> request -> graph-state hops all exist (DIG-4459)."""
    from types import SimpleNamespace

    from digigraph.http_api.context import _digi_fields_from_request
    from digigraph.models import WorkflowRequest
    from digigraph.workflow import _initial_graph_state

    monkeypatch.setenv(
        "DIGI_TENANT_CORPUS_MAP",
        json.dumps(
            {
                TENANT: {"digisearchIndex": "tenant-help"},
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
                    tenant_slug_verified=True,
                    project_id=None,
                    jti=None,
                ),
            ),
            headers={},
        )

    updates = _digi_fields_from_request(_request(TENANT))
    assert updates["skill_pack"] == TENANT
    assert tuple(updates["skills"]) == EXPECTED
    request = WorkflowRequest(prompt="hi", **{k: v for k, v in updates.items() if v is not None})
    state = _initial_graph_state(request, "wf-skills")
    assert state["skill_pack"] == TENANT
    assert tuple(state["skills"]) == EXPECTED

    house = _digi_fields_from_request(_request("house"))
    assert house["skill_pack"] is None
    assert house["skills"] == []


@pytest.mark.unit
def test_research_appends_the_bundle_only_for_a_tenant_with_skills():
    import inspect

    from digigraph.graph import research

    source = inspect.getsource(research)
    assert (
        "if _tenant_skill_ids and _tenant_skill_pack and SKILL_LIBRARY_SKILL_ID not in skill_ids:\n"
        "        skill_ids.append(SKILL_LIBRARY_SKILL_ID)" in source
    ), "bundle id is not appended behind the tenant-skills guard"
    assert "_allowed_names | SKILL_LIBRARY_TOOL_NAMES" in source
    assert "if SKILL_LIBRARY_SKILL_ID in skill_ids:" in source
