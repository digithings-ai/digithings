"""The generated flat view of the layered migration chain (DIG-4449).

D-Q6′ (DIG-3694) layered the chain into engine/ and prod/; the Supabase CLI
reads only the top level of supabase/migrations, so `dt up` builds a flat view
of it. These tests pin the order (engine then prod, each in filename order) and
prove the generated tree is correct against the real repository chain.
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

    entries = sorted(p.name for p in (dest / "supabase" / "migrations").iterdir())
    assert entries == ["001_a.sql", "002_b.sql"]
    link = dest / "supabase" / "migrations" / "001_a.sql"
    assert link.is_symlink()
    assert link.resolve() == (project / "migrations" / "engine" / "001_a.sql").resolve()
    # the CLI also reads these from the project dir
    for name in ("config.toml", "seed.sql", "roles.sql", "functions"):
        assert (dest / "supabase" / name).is_symlink()


def test_materialize_is_idempotent(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")

    first = supabase_flat.materialize(tmp_path)
    second = supabase_flat.materialize(tmp_path)

    assert first == second
    entries = sorted(p.name for p in (second / "supabase" / "migrations").iterdir())
    assert entries == ["001_a.sql"]


def test_materialize_drops_a_stale_link_when_a_migration_moves_layer(tmp_path):
    project = _fake_project(tmp_path)
    (project / "migrations" / "engine" / "001_a.sql").write_text("", encoding="utf-8")
    supabase_flat.materialize(tmp_path)

    (project / "migrations" / "engine" / "001_a.sql").unlink()
    (project / "migrations" / "prod" / "001_a.sql").write_text("", encoding="utf-8")
    dest = supabase_flat.materialize(tmp_path)

    link = dest / "supabase" / "migrations" / "001_a.sql"
    assert link.resolve() == (project / "migrations" / "prod" / "001_a.sql").resolve()


def test_materialize_refuses_to_write_inside_the_real_project(tmp_path):
    _fake_project(tmp_path)
    with pytest.raises(ValueError):
        supabase_flat.materialize(tmp_path, tmp_path / supabase_flat.PROJECT_REL)


def test_the_real_chain_flattens_to_the_layered_order(tmp_path):
    """The generator run against the real repo yields exactly engine-sorted + prod-sorted."""
    project = REPO_ROOT / supabase_flat.PROJECT_REL
    engine = sorted(p.name for p in (project / "migrations" / "engine").glob("*.sql"))
    prod = sorted(p.name for p in (project / "migrations" / "prod").glob("*.sql"))

    dest = supabase_flat.materialize(REPO_ROOT, tmp_path / "flat")
    flat = sorted(p.name for p in (dest / "supabase" / "migrations").iterdir())

    assert flat == sorted(engine + prod)
    assert len(flat) == len(engine) + len(prod) == len(set(flat)), "flattening must not collide files"
    assert [p.name for p in supabase_flat.ordered_migrations(project)] == engine + prod
