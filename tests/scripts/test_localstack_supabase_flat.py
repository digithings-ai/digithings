"""The generated flat view of the layered migration chain (DIG-4449).

D-Q6′ (DIG-3694) layered the chain into engine/ and prod/; the Supabase CLI
reads only the top level of supabase/migrations, so `dt up` builds a flat view
of it. These tests pin the order (engine then prod, each in filename order) and
prove the generated tree is correct against the real repository chain.

The CLI sorts the flat directory by file name, so the generated links are
numbered 001..N in the order the harnesses apply (engine first, then prod) and
keep the canonical file name in the stem. The invariant these tests pin is the
one that matters: read the flat directory the way the CLI reads it (sorted by
name) and the files resolve to the harness order.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.localstack import supabase_flat

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _fake_project(root: Path) -> Path:
    """A minimal stand-in with the source layout the generator reads."""
    project = root / supabase_flat.PROJECT_REL
    (project / "migrations" / "engine").mkdir(parents=True)
    (project / "migrations" / "prod").mkdir(parents=True)
    (project / "config.toml").write_text('project_id = "test"\n', encoding="utf-8")
    (project / "seed.sql").write_text("select 1;\n", encoding="utf-8")
    (project / "roles.sql").write_text("select 1;\n", encoding="utf-8")
    (project / "functions").mkdir()
    return project


def _cli_order(dest: Path) -> list:
    """The migrations the CLI would apply: the flat dir sorted by file name."""
    migrations = dest / "supabase" / "migrations"
    return [p.resolve() for p in sorted(migrations.iterdir(), key=lambda p: p.name)]


def test_ordered_migrations_is_engine_then_prod_in_filename_order(tmp_path):
    project = _fake_project(tmp_path)
    for name in ("003_c.sql", "001_a.sql", "010_j.sql"):
        (project / "migrations" / "engine" / name).write_text("", encoding="utf-8")
    for name in ("002_b.sql", "012_l.sql"):
        (project / "migrations" / "prod" / name).write_text("", encoding="utf-8")

    names = [p.name for p in supabase_flat.ordered_migrations(project)]
    assert names == ["001_a.sql", "003_c.sql", "010_j.sql", "002_b.sql", "012_l.sql"]


def test_materialize_flattens_the_layered_chain(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")
    (project / "migrations" / "prod" / "002_b.sql").write_text("", encoding="utf-8")

    dest = supabase_flat.materialize(tmp_path)

    # the CLI reads the flat dir sorted by name: engine first, then prod
    assert _cli_order(dest) == [
        (project / "migrations" / "engine" / "001_a.sql").resolve(),
        (project / "migrations" / "prod" / "002_b.sql").resolve(),
    ]
    entries = list((dest / "supabase" / "migrations").iterdir())
    assert all(p.is_symlink() for p in entries)
    # the CLI also reads these from the project dir. config.toml is a REAL
    # copy, not a link: it carries the Supabase ports and the CLI has no port
    # flags, so the generated tree has to carry them (DIG-4501). A link would
    # send the rewrite into the checked-in file.
    for name in ("seed.sql", "roles.sql", "functions"):
        assert (dest / "supabase" / name).is_symlink()
    config = dest / "supabase" / "config.toml"
    assert not config.is_symlink()
    assert config.read_text() == (project / "config.toml").read_text()


def test_materialize_writes_a_port_rewritten_config_copy(tmp_path):
    """The generated config.toml carries the ports; the checked-in one does not move."""
    project = _fake_project(tmp_path)
    (project / "config.toml").write_text(
        'project_id = "test"\n'
        "\n"
        "[api]\n"
        "port = 54321\n"
        "\n"
        "[db]\n"
        "port = 54322\n"
        "shadow_port = 54320\n"
        "\n"
        "[db.pooler]\n"
        "enabled = false\n"
        "port = 54329\n"
        "\n"
        "[studio]\n"
        "port = 54323\n",
        encoding="utf-8",
    )
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")

    dest = supabase_flat.materialize(tmp_path, api_port=55321)

    written = (dest / "supabase" / "config.toml").read_text()
    assert "port = 55321" in written
    assert "port = 55322" in written
    assert "shadow_port = 55320" in written
    assert "port = 55329" in written
    assert "port = 55323" in written
    assert "port = 54321" not in written
    assert 'project_id = "test"' in written
    # the checked-in file is untouched: it still carries the canonical ports
    assert "port = 54321" in (project / "config.toml").read_text()
    assert (project / "config.toml").is_file()


def test_materialize_is_idempotent(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")

    first = supabase_flat.materialize(tmp_path)
    second = supabase_flat.materialize(tmp_path)

    assert first == second
    assert _cli_order(second) == [
        (project / "migrations" / "engine" / "001_a.sql").resolve()
    ]


def test_materialize_drops_a_stale_link_when_a_migration_moves_layer(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")
    supabase_flat.materialize(tmp_path)

    (project / "migrations" / "engine" / "001_a.sql").unlink()
    (project / "migrations" / "prod" / "001_a.sql").write_text("", encoding="utf-8")
    dest = supabase_flat.materialize(tmp_path)

    assert _cli_order(dest) == [
        (project / "migrations" / "prod" / "001_a.sql").resolve()
    ]


def test_materialize_refuses_to_write_inside_the_real_project(tmp_path):
    _fake_project(tmp_path)
    with pytest.raises(ValueError):
        supabase_flat.materialize(tmp_path, tmp_path / supabase_flat.PROJECT_REL)


def test_materialize_refuses_to_write_into_an_ancestor_of_the_project(tmp_path):
    """`--dest digiquant` is one word away from the real project: refuse it."""
    project = _fake_project(tmp_path)
    ancestor = tmp_path / "digiquant"
    assert project.parent == ancestor  # the ancestor holds the real project dir
    with pytest.raises(ValueError):
        supabase_flat.materialize(tmp_path, ancestor)


def test_a_stray_top_level_migration_is_refused(tmp_path):
    """The chain's own guard rejects a stray top-level *.sql; the flat view must too."""
    project = _fake_project(tmp_path)
    (project / "migrations" / "099_stray.sql").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        supabase_flat.materialize(tmp_path)


def test_duplicate_migration_names_across_layers_are_refused(tmp_path):
    """A name present in both layers would silently drop one migration."""
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "003_x.sql").write_text("", encoding="utf-8")
    (project / "migrations" / "prod" / "003_x.sql").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        supabase_flat.materialize(tmp_path)


def test_a_deleted_linked_source_leaves_no_stale_link(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")
    dest = supabase_flat.materialize(tmp_path)
    assert (dest / "supabase" / "roles.sql").is_symlink()

    (project / "roles.sql").unlink()
    dest = supabase_flat.materialize(tmp_path)

    assert not (dest / "supabase" / "roles.sql").exists()
    assert not (dest / "supabase" / "roles.sql").is_symlink()


def test_the_generated_root_carries_the_projects_docs_directory(tmp_path):
    """The CLI resolves the workdir as the project root.

    `supabase start` reads `docs/schemas/execution_policy.v1.json` from the
    root of the project it is pointed at, so the generated tree has to carry a
    link to the real project's docs directory. Without it the CLI aborts with
    "failed to read file: .../docs/schemas/execution_policy.v1.json".
    """
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")
    docs = project.parent / "docs"
    (docs / "schemas").mkdir(parents=True)
    (docs / "schemas" / "execution_policy.v1.json").write_text("{}", encoding="utf-8")

    dest = supabase_flat.materialize(tmp_path)

    link = dest / "docs"
    assert link.is_symlink()
    assert link.resolve() == docs.resolve()
    assert (link / "schemas" / "execution_policy.v1.json").exists()


def test_a_missing_docs_directory_leaves_no_stale_link(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")
    docs = project.parent / "docs"
    docs.mkdir()
    dest = supabase_flat.materialize(tmp_path)
    assert (dest / "docs").is_symlink()

    docs.rmdir()
    dest = supabase_flat.materialize(tmp_path)

    assert not (dest / "docs").exists()
    assert not (dest / "docs").is_symlink()


def test_the_real_chain_flattens_to_the_layered_order(tmp_path):
    """Against the real chain: the CLI's read order resolves to engine then prod."""
    project = REPO_ROOT / supabase_flat.PROJECT_REL
    engine = sorted(p.name for p in (project / "migrations" / "engine").glob("*.sql"))
    prod = sorted(p.name for p in (project / "migrations" / "prod").glob("*.sql"))

    dest = supabase_flat.materialize(REPO_ROOT, tmp_path / "flat")
    resolved = _cli_order(dest)

    expected = [
        (project / "migrations" / "engine" / name).resolve() for name in engine
    ] + [(project / "migrations" / "prod" / name).resolve() for name in prod]
    assert resolved == expected
    assert len(resolved) == len(engine) + len(prod) == len(set(resolved))
