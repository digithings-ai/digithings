"""Guards for the strategy lab facade (``digiquant.strategies.lab``).

Four properties are load-bearing and each has a test that fails when the
property is removed:

1. the facade adds no eager submodule import on top of what the parent package
   already does (it is lazy, not merely "small");
2. touching every curated name imports no Nautilus module, so the toolkit's
   API works without the ``nautilus`` extra;
3. module identity survives -- ``lab.X is sdca.X`` and a patch on either path is
   visible from the other, which is what keeps ~200 importing files and the
   compatibility shim working;
4. the curated names stay unambiguous, which is an AST census rather than a
   runtime check so a collision is caught at collection time.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import digiquant.strategies.lab as lab
import pytest

import digiquant

pytestmark = pytest.mark.unit

LAB_DIR = Path(lab.__path__[0]).resolve()
SRC_ROOT = Path(digiquant.__file__).resolve().parent.parent

#: The two modules that import ``nautilus_trader`` at module import time.
NAUTILUS_MODULES = ("nautilus_evaluator", "nautilus_strategy")
HAS_NAUTILUS = importlib.util.find_spec("nautilus_trader") is not None

#: Every submodule on disk, ``__init__`` excluded.
MODULE_NAMES = tuple(sorted(p.stem for p in LAB_DIR.glob("*.py") if p.stem != "__init__"))

_PROBE = """
import importlib.util as _util
import json, sys

_real_find_spec = _util.find_spec


def _fake_find_spec(name, *args, **kwargs):
    # Hide the optional dependency so the parent package's gate takes its skip
    # branch. Without this the parent imports lab.nautilus_strategy itself and
    # the laziness measurement has no clean baseline to compare against.
    if name == "nautilus_trader" or name.startswith("nautilus_trader."):
        return None
    return _real_find_spec(name, *args, **kwargs)


_util.find_spec = _fake_find_spec

import @MODULE@  # noqa: F401

loaded = sorted(m for m in sys.modules if m.startswith("digiquant.strategies.lab."))
print("RESULT " + json.dumps({
    "loaded": loaded,
    "has_package": "digiquant.strategies.lab" in sys.modules,
}))
"""

_CURATED_PROBE = """
import importlib.util as _util

_real_find_spec = _util.find_spec


def _fake_find_spec(name, *args, **kwargs):
    # Hide the optional dependency BEFORE the package is imported, so
    # digiquant.strategies.__init__ takes its skip branch deterministically
    # whether or not nautilus_trader happens to be installed here.
    if name == "nautilus_trader" or name.startswith("nautilus_trader."):
        return None
    return _real_find_spec(name, *args, **kwargs)


_util.find_spec = _fake_find_spec

import json, sys
import digiquant.strategies.lab as lab

names = sorted(lab.__all__)
resolved = 0
for name in names:
    getattr(lab, name)
    resolved += 1
print("RESULT " + json.dumps({
    "declared": len(names),
    "resolved": resolved,
    "nautilus": sorted(
        m for m in sys.modules
        if m == "nautilus_trader" or m.startswith("nautilus_trader.")
    ),
    "lab_nautilus": sorted(
        m for m in sys.modules if m.startswith("digiquant.strategies.lab.nautilus")
    ),
}))
"""


def _run_fresh(code: str) -> dict:
    """Run ``code`` in a fresh interpreter and return its ``RESULT`` payload."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) + ((os.pathsep + existing) if existing else "")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    assert proc.returncode == 0, (
        f"fresh-interpreter probe failed: rc={proc.returncode}\n"
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-4000:]}"
    )
    results = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert results, f"probe printed no RESULT line: {proc.stdout[-2000:]}"
    return json.loads(results[-1][len("RESULT ") :])


def _definitions() -> dict[str, set[str]]:
    """Public top-level names in each module, keyed by name -> defining modules."""
    where: dict[str, set[str]] = {}
    for path in sorted(LAB_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names: list[str] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            for name in names:
                if not name.startswith("_"):
                    where.setdefault(name, set()).add(path.stem)
    return where


def test_lab_is_a_regular_package() -> None:
    """The facade needs a file; a namespace package cannot carry ``__getattr__``."""
    assert lab.__file__ is not None
    assert Path(lab.__file__).name == "__init__.py"
    assert LAB_DIR.name == "lab"
    # Flat at depth 1 is load-bearing: the engine resolves settings.json and its
    # sidecars with Path(__file__).resolve().parents[1] / parents[0].
    assert not any(p.is_dir() and p.name != "__pycache__" for p in LAB_DIR.iterdir())


def test_importing_the_facade_imports_no_submodule() -> None:
    """Fresh interpreters with Nautilus hidden, so the measurement is clean."""
    parent_only = _run_fresh(_PROBE.replace("@MODULE@", "digiquant.strategies"))
    with_facade = _run_fresh(_PROBE.replace("@MODULE@", "digiquant.strategies.lab"))

    # A firing control on the instrument itself: if the parent ever starts
    # importing a lab submodule, the baseline is polluted and the assertion
    # below would pass for the wrong reason.
    assert parent_only["loaded"] == [], (
        "importing the parent package already pulls in a lab submodule, so the "
        f"laziness measurement is void: {parent_only['loaded']}"
    )
    assert with_facade["has_package"] is True, "the facade was not actually imported"
    assert with_facade["loaded"] == [], (
        "importing the facade eagerly imported submodules: "
        f"{with_facade['loaded']}. The facade must resolve on attribute access only."
    )


def test_no_curated_name_comes_from_a_nautilus_module() -> None:
    """Exact and environment-independent: the map itself never names Nautilus.

    A dynamic check cannot see this on a host where ``nautilus_trader`` is
    installed, because ``digiquant.strategies.__init__`` imports the wrapper
    anyway -- so the static property is asserted directly, and the behavioural
    half is covered by the hidden-Nautilus probe below.
    """
    referenced = {module_name for module_name, _attr in lab._NAMES.values()}
    assert sorted(referenced & set(NAUTILUS_MODULES)) == [], (
        "a curated name is drawn from a module that imports nautilus_trader at "
        f"import time: {sorted(referenced & set(NAUTILUS_MODULES))}"
    )
    assert sorted(referenced - set(MODULE_NAMES)) == [], (
        "the facade names a submodule that is not on disk: "
        f"{sorted(referenced - set(MODULE_NAMES))}"
    )


def test_the_whole_curated_api_resolves_with_nautilus_hidden() -> None:
    """The toolkit's stated API must work without the ``nautilus`` extra.

    ``nautilus_trader`` is hidden from the import system *before* the package is
    imported, so the parent's ``find_spec`` gate takes its skip branch. If any
    curated name needs Nautilus, the probe raises and this fails loudly -- which
    is exactly what hoisting ``SdcaStrategy`` would do.
    """
    result = _run_fresh(_CURATED_PROBE)

    assert result["declared"] > 40, (
        f"only {result['declared']} curated names -- the census looks broken"
    )
    assert result["resolved"] == result["declared"], (
        f"not every curated name resolved: {result['resolved']}/{result['declared']}"
    )
    assert result["nautilus"] == [], (
        f"nautilus_trader was imported despite being hidden: {result['nautilus']}"
    )
    assert result["lab_nautilus"] == [], (
        "a Nautilus wrapper module was imported while the extra was absent: "
        f"{result['lab_nautilus']}"
    )


@pytest.mark.parametrize("name", sorted(lab._NAMES))
def test_curated_name_resolves_to_its_module_attribute(name: str) -> None:
    module_name, attribute = lab._NAMES[name]
    module = importlib.import_module(f"digiquant.strategies.lab.{module_name}")
    assert lab.__getattr__(name) is getattr(module, attribute)


def test_every_curated_name_is_declared_by_the_module_it_names() -> None:
    """Pins the map against a rename, without importing anything."""
    where = _definitions()
    assert len(where) > 200, (
        f"AST census found only {len(where)} public names -- the census is broken, not the facade"
    )
    wrong_module = sorted(
        (name, module_name)
        for name, (module_name, attribute) in lab._NAMES.items()
        if module_name not in where.get(name, set()) or attribute != name
    )
    assert wrong_module == [], (
        "curated entries name a module that does not define them (or rename the "
        f"attribute): {wrong_module}"
    )


def test_no_curated_name_is_defined_in_more_than_one_module() -> None:
    """Eight names in this package are ambiguous; hoisting one would pick a side."""
    where = _definitions()
    ambiguous = {name: sorted(where[name]) for name in lab._NAMES if len(where.get(name, ())) > 1}
    assert ambiguous == {}, (
        "a curated name is defined in more than one module, so the facade would "
        f"silently pick one: {ambiguous}"
    )
    # Control: the census must be able to see ambiguity at all.
    known_ambiguous = sorted(n for n, mods in where.items() if len(mods) > 1)
    assert "load_coefficients" in known_ambiguous, (
        "the ambiguity detector no longer finds a known-ambiguous name "
        f"(found {known_ambiguous}) -- the census is broken, not the facade"
    )


def test_module_handles_are_the_same_objects_as_direct_imports() -> None:
    # A floor plus a known member, not an exact count: the census is a control
    # on the instrument (can the walk see modules at all?), and an exact pin
    # would make every new lab module a test edit.
    assert len(MODULE_NAMES) >= 30, f"module census too small to be real: {MODULE_NAMES}"
    assert "backtest" in MODULE_NAMES, f"census missed a known module: {MODULE_NAMES}"
    for module_name in MODULE_NAMES:
        if module_name in NAUTILUS_MODULES and not HAS_NAUTILUS:
            continue
        direct = importlib.import_module(f"digiquant.strategies.lab.{module_name}")
        assert getattr(lab, module_name) is direct


def test_legacy_sdca_modules_are_the_same_objects_as_their_lab_twins() -> None:
    """``sdca.X is lab.X`` -- the compatibility shim's whole contract."""
    for module_name in MODULE_NAMES:
        if module_name in NAUTILUS_MODULES and not HAS_NAUTILUS:
            continue
        legacy = importlib.import_module(f"digiquant.strategies.sdca.{module_name}")
        assert legacy is getattr(lab, module_name)


def test_alias_modules_report_a_path_under_the_lab_directory() -> None:
    for module_name in MODULE_NAMES:
        if module_name in NAUTILUS_MODULES and not HAS_NAUTILUS:
            continue
        module = getattr(lab, module_name)
        assert Path(module.__file__).resolve().parent == LAB_DIR


def test_a_patch_on_either_path_is_visible_from_the_other() -> None:
    legacy = importlib.import_module("digiquant.strategies.sdca.backtest")
    modern = importlib.import_module("digiquant.strategies.lab.backtest")
    assert legacy is modern

    sentinel = object()
    with mock.patch.object(legacy, "run_backtest", sentinel):
        assert modern.run_backtest is sentinel
    with mock.patch.object(modern, "run_backtest", sentinel):
        assert legacy.run_backtest is sentinel
    assert modern.run_backtest is not sentinel, "the patch did not unwind"


def test_resource_paths_still_resolve_from_inside_the_lab_directory() -> None:
    """``parents[1] / "settings.json"`` must keep meaning ``strategies/settings.json``."""
    strategies_dir = LAB_DIR.parent

    stage_0 = importlib.import_module("digiquant.strategies.lab.stage_0")
    assert Path(stage_0.__file__).resolve().parents[1] == strategies_dir
    assert (Path(stage_0.__file__).resolve().parents[1] / "settings.json").is_file()
    assert (strategies_dir / "settings.json").is_file()

    presets = importlib.import_module("digiquant.strategies.lab.presets")
    assert (Path(presets.__file__).resolve().parent / "presets.json").is_file()


def test_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        lab.definitely_not_a_module_or_name


def test_all_is_the_curated_api_and_dir_lists_modules() -> None:
    assert set(lab.__all__) == set(lab._NAMES)
    assert lab.__all__ == sorted(lab.__all__)
    listed = lab.__dir__()
    assert set(lab._NAMES) <= set(listed)
    assert set(MODULE_NAMES) <= set(listed)
