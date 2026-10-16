"""The integrations band must be generated from the dependencies, never typed.

The two "connected package" rows on the digiquant.io integrations band were a
hand-maintained literal naming providers this tree has no dependency on. Nothing
noticed, because a literal only goes stale when someone remembers to edit it:
DIG-2814 dropped two of those providers from the chart feed and the rows stayed.

`scripts/build_providers_band.py` answers the question from the manifests and the
source imports, and this gate is what stops the answer going stale. It asserts the
committed JSON equals a fresh run, and it asserts the generator's two arms each
*discriminate* -- a green "is current" from a generator that can never fire is the
failure mode this file exists to catch.

It also pins the seam the other way: the band imports the JSON, so nobody can
re-inline the list and leave this gate happily green on a file nothing reads.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_providers_band.py"
BAND_JSON = REPO_ROOT / "apps/digiquant-web/app/_bands/integrations.providers.json"
BAND_TSX = REPO_ROOT / "apps/digiquant-web/app/_bands/integrations.tsx"
MARKS_TSX = REPO_ROOT / "apps/digiquant-web/components/integrations/marks.tsx"


def _load_generator():
    """Import the script by path.

    The module is registered in ``sys.modules`` before ``exec_module``: dataclasses
    resolves the KW_ONLY sentinel through ``sys.modules[cls.__module__].__dict__``,
    so a dataclass loaded without registration raises ``AttributeError: NoneType
    object has no attribute __dict__`` from inside dataclasses.py -- a traceback
    that points at the file under test rather than at the loader.
    """
    spec = importlib.util.spec_from_file_location("build_providers_band", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_generator()


@pytest.fixture(scope="module")
def committed(gen) -> dict:
    return json.loads(BAND_JSON.read_text(encoding="utf-8"))


# --- the gate itself ---------------------------------------------------------


def test_the_committed_json_equals_a_fresh_run(gen, committed):
    """What CI turns red on. `render` is compared, not `build`, so key order and
    trailing newline are part of the contract -- a reformatted file is a diff the
    next generator run would reintroduce."""
    assert gen.render(gen.build(gen.REPO_ROOT)) == BAND_JSON.read_text(encoding="utf-8")


def test_the_committed_json_is_not_empty(committed):
    """A generator that resolved nothing would render a valid, current, EMPTY file
    and pass the gate above. The band would silently lose every row."""
    ids = [p["id"] for p in committed["providers"]]
    assert ids, "the generator produced no providers at all -- the arms cannot both be false"
    assert len(ids) == len(set(ids)), f"duplicate provider ids: {ids}"


# --- non-vacuity: the two arms must each be able to say no --------------------


def test_the_declared_arm_reads_a_real_manifest(gen):
    """FRED is declared: `digiquant/pyproject.toml`'s `m2` extra pins fredapi.
    Without this, FRED's absence from the band could be caused by a parser that
    silently returned nothing for every manifest."""
    surfaces = gen.declared_packages(gen.REPO_ROOT)
    assert "fredapi" in surfaces, "fredapi must be visible as declared"
    assert any("digiquant/pyproject.toml" in s for s in surfaces["fredapi"]), surfaces["fredapi"]


def test_the_imported_arm_reads_real_source(gen):
    """The control that makes the absence meaningful: `alpaca` is a direct import
    in digiquant/src/digiquant/brokers/alpaca.py, so the import scan reaches
    non-test source. Its absence from the band would then be a bug, not a fact."""
    modules = gen.imported_modules(gen.REPO_ROOT)
    assert "alpaca" in modules
    assert "supabase" in modules
    assert "yfinance" in modules


def test_the_import_arm_matches_a_dotted_module_path(gen):
    """`from alpaca.trading.client import TradingClient` names a dotted module. An
    import pattern anchored on a non-dotted name never matches it, which silently
    dropped a real dependency while the JSON still looked plausible. Pin the shape
    the code actually writes."""
    source = REPO_ROOT / "digiquant/src/digiquant/brokers/alpaca.py"
    text = source.read_text(encoding="utf-8")
    assert re.search(r"^\s*from alpaca\.\w+\.\w+ import", text, re.M), (
        "expected a dotted alpaca import in brokers/alpaca.py -- if this file moved, "
        "the import-arm fixture needs repointing"
    )
    assert "alpaca" in gen.imported_modules(gen.REPO_ROOT)


def test_a_declared_but_unimported_package_is_not_a_provider(gen, committed):
    """The rule, stated on the one case that distinguishes it. fredapi is declared
    in a real extra and imported by nothing, because `m2` reads the sealed R2
    `fred__M2SL` parquet. Carrying the dependency is not the same as using it."""
    declared = gen.declared_packages(gen.REPO_ROOT)
    modules = gen.imported_modules(gen.REPO_ROOT)
    assert "fredapi" in declared
    assert "fredapi" not in modules
    assert "fred" not in {p["id"] for p in committed["providers"]}


def test_a_package_no_manifest_declares_is_not_a_provider(gen, committed):
    """Coinbase, Interactive Brokers, Kraken, Tradier and Binance have no package
    at all -- the IBKR extra pins httpx and no IBKR client -- so no generator run
    can bring those rows back."""
    declared = gen.declared_packages(gen.REPO_ROOT)
    for missing in ("coinbase-py", "ibkr", "kraken", "tradier", "binance"):
        assert missing not in declared, f"{missing} is declared after all -- re-read the census"
    shipped = {p["id"] for p in committed["providers"]}
    for gone in ("fred", "coinbase", "ibkr", "kraken", "tradier", "binance"):
        assert gone not in shipped


# --- non-vacuity: the generator must not be counting its own table -------------


def test_the_generator_is_excluded_from_its_own_import_scan(gen):
    """The vocabulary in PROVIDERS is a quoted tuple of module names. A scan that
    matched any quoted string found `fredapi` in the generator's own source and
    shipped FRED. The exclusion is a named constant, repo-relative, so widening it
    is a visible diff -- and a bare filename would never match the posix paths the
    walk compares against, which is how this guard sat inert for one run."""
    assert gen.EXCLUDED_FROM_SCAN == frozenset({f"scripts/{SCRIPT.name}"})


def test_the_exclusion_actually_removes_a_file_from_the_walk(gen):
    """The control that would have caught the inert guard: the excluded file must be
    absent, and the walk must still return files. Either half alone is decoration."""
    excluded = {Path(p).name for p in gen.iter_source_files(gen.REPO_ROOT)}
    walked = {Path(p).name for p in gen.iter_source_files(gen.REPO_ROOT, exclude=frozenset())}
    assert SCRIPT.name not in excluded, (
        "the exclusion is inert -- the generator counts its own table"
    )
    assert SCRIPT.name in walked, "control: the file must be reachable when not excluded"
    assert excluded, "the source walk returned nothing -- both arms would read empty"
    assert excluded < walked, "excluding the generator must shrink the walk"


def test_the_test_filter_has_files_to_remove(gen):
    """The filter over test paths is currently defensive, not load-bearing: no test
    file imports a mapped package, so switching it off changes no row. That makes it
    exactly the guard that can never fail, so prove it has work to do -- and name
    the honest status rather than implying it pins a verdict."""
    real_is_test = gen._is_test
    unfiltered: set[str] = set()
    try:
        # iter_source_files resolves _is_test as a module global at call time, so
        # neutering it here measures the filter's real workload. Differencing two
        # ordinary walks would only ever surface the self-exclusion.
        gen._is_test = lambda path: False
        unfiltered = {
            p.relative_to(gen.REPO_ROOT).as_posix() for p in gen.iter_source_files(gen.REPO_ROOT)
        }
    finally:
        gen._is_test = real_is_test
    walked = {p.relative_to(gen.REPO_ROOT).as_posix() for p in gen.iter_source_files(gen.REPO_ROOT)}
    removed = unfiltered - walked
    assert removed, "the test filter removed nothing -- it cannot be load-bearing"
    assert all(real_is_test(Path(rel)) for rel in removed), (
        f"the filter removed non-test files: {sorted(removed)[:5]}"
    )
    assert walked, "the walk returned nothing"


# --- the seam: the band actually reads the JSON -------------------------------


def test_the_band_imports_the_generated_json(gen):
    """A gate on a file nothing reads is green forever. The band must import it."""
    text = BAND_TSX.read_text(encoding="utf-8")
    assert 'from "./integrations.providers.json"' in text, (
        "integrations.tsx must import the generated list; re-inlining the rows "
        "defeats the generator and leaves this gate green on dead output"
    )


def test_the_band_hardcodes_no_row_provider_ids():
    """No row provider id may be typed into the band again. Scoped to the
    `RowProviderId` vocabulary rather than to all `id:` literals, because DRIVERS
    legitimately carry their own hand-written ids (`gloomberb`, `luxalgo`,
    `nautilus`) on the cards above the rows -- those are a different surface."""
    marks_source = MARKS_TSX.read_text(encoding="utf-8")
    union = set(
        re.findall(
            r'"([a-z]+)"',
            re.search(r"export type RowProviderId\s*=\s*([^;]+);", marks_source, re.S).group(1),
        )
    )
    assert union, "RowProviderId parsed empty -- the check would pass vacuously"
    text = BAND_TSX.read_text(encoding="utf-8")
    typed = {m for m in re.findall(r'id:\s*"([a-z]+)"', text) if m in union}
    assert not typed, f"row provider ids are typed into the band again: {sorted(typed)}"


# --- the logo flags ----------------------------------------------------------


def test_every_generated_row_carries_a_logo_path_or_a_missing_flag(committed):
    """DIG-2861's acceptance, in the shape the generator can prove: a row either
    names the official monochrome mark it draws, or says it has none. A third
    shape -- silently nothing -- is the gap this rules out."""
    for provider in committed["providers"]:
        logo = provider["logo"]
        assert ("slug" in logo) != ("missing" in logo), provider["id"]
        if logo.get("missing"):
            assert logo["reason"], provider["id"]
        else:
            assert logo["source"].startswith("simple-icons@"), provider["id"]


def test_the_logo_registry_is_the_row_marks_object(committed):
    """The flag is derived from ROW_MARKS in marks.tsx, not from a second hardcoded
    list that could drift from it. Point it at that file or say a mark is missing."""
    for provider in committed["providers"]:
        logo = provider["logo"]
        if logo.get("missing"):
            continue
        assert logo["registry"] == MARKS_TSX.relative_to(REPO_ROOT).as_posix()
        marks_source = MARKS_TSX.read_text(encoding="utf-8")
        assert re.search(rf"\b{provider['id']}:\s*si", marks_source), (
            f"{provider['id']} claims a mark that ROW_MARKS does not register"
        )


# --- the union stays in step -------------------------------------------------


def test_every_generated_id_is_covered_by_the_row_provider_union(committed):
    """marks.tsx keeps a hand-written union (the marks are direct imports, so the
    generator cannot own it). A generated id the union does not name would be a
    type error at build time -- but tests are excluded from tsconfig, so pin it
    here instead of trusting a compiler that never sees it."""
    marks_source = MARKS_TSX.read_text(encoding="utf-8")
    match = re.search(r"export type RowProviderId\s*=\s*([^;]+);", marks_source, re.S)
    assert match, "RowProviderId union not found in marks.tsx"
    union = set(re.findall(r'"([a-z]+)"', match.group(1)))
    assert union, "RowProviderId parsed empty -- the regex matched, the content did not"
    for provider in committed["providers"]:
        assert provider["id"] in union, (
            f"{provider['id']} is generated but absent from RowProviderId: {sorted(union)}"
        )


def test_the_union_carries_no_provider_the_generator_dropped():
    """The other direction. `fred` outlived its row for a release: the id sat in
    the union long after the row was deleted, so the type kept advertising a
    provider the band no longer claimed."""
    marks_source = MARKS_TSX.read_text(encoding="utf-8")
    match = re.search(r"export type RowProviderId\s*=\s*([^;]+);", marks_source, re.S)
    union = set(re.findall(r'"([a-z]+)"', match.group(1)))
    for dead in ("fred", "coinbase", "ibkr", "kraken", "tradier", "binance"):
        assert dead not in union, f"{dead} still advertised by RowProviderId: {sorted(union)}"


def test_generated_surface_strings_name_manifests_that_exist(committed):
    """`declaredIn` is the row's receipt. A surface naming a file that is not there
    would make the receipt unreadable, and a reader has no way to check it."""
    for provider in committed["providers"]:
        assert provider["declaredIn"], f"{provider['id']} shipped without a receipt"
        for surface in provider["declaredIn"]:
            manifest = surface.split(":", 1)[0].strip()
            assert (REPO_ROOT / manifest).is_file(), f"{provider['id']} -> {manifest} is missing"
