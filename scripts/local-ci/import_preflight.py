#!/usr/bin/env python3
"""import_preflight: refuse to tick when a module the runner imports is absent.

DIG-5585. The runner imports its helpers with a fallback:

    try:
        import review_applied
    except ImportError:
        review_applied = None

and each helper fails closed when it is None. That is the right answer to a
single missing fact, but the wrong answer to a broken install: on 24 Oct 2026
a runner checkout without ``scripts/review_pass_filter.py`` made every
``review-applied`` row red with "no review pass left comments", so the status
blamed the review while the missing file was the fault (DIG-4674 found it).

This module resolves, at start, every module the runner imports - transitively,
including the shared modules one directory up and the modules the runner loads
by file path - and refuses the tick when one is absent. The refusal names the
missing module and the module that imports it, so a broken install reads as a
broken install instead of as a failed review.

Stdlib only. Check an install without ticking it:

    /usr/bin/python3 scripts/local-ci/import_preflight.py [path/to/local_ci.py]

Exit 0 means every import resolves; 78 (EX_CONFIG) means the install is
incomplete and the runner must not tick.
"""

from __future__ import annotations

import ast
import os
import sys

#: EX_CONFIG, the exit code launch_guard.py already uses for "refuse to run".
EXIT_CONFIG = 78

#: Modules the runner loads by file path (``spec_from_file_location`` in
#: local_ci.py), which an import scan cannot see. Keep this in step with the
#: runner; a module named here must exist next to the runner.
LOADED_BY_PATH = ("check_required_context_producers.py",)

_STDLIB = None


def _stdlib_names():
    """Top-level names of the standard library, for this interpreter.

    ``sys.stdlib_module_names`` exists from 3.10; the host runs
    /usr/bin/python3 (3.9), so the stdlib directory is listed as well.
    """
    global _STDLIB
    if _STDLIB is not None:
        return _STDLIB
    names = set(getattr(sys, "stdlib_module_names", ()))
    # ``sys`` and ``time`` are compiled into the interpreter: they have no file
    # in the stdlib directory, so the directory listing alone misses them.
    names.update(getattr(sys, "builtin_module_names", ()))
    try:
        import sysconfig

        stdlib = sysconfig.get_paths().get("stdlib") or ""
    except (ImportError, AttributeError, KeyError, OSError):
        stdlib = ""
    if stdlib and os.path.isdir(stdlib):
        for entry in os.listdir(stdlib):
            if entry in ("site-packages", "dist-packages"):
                continue
            names.add(entry.split(".")[0])
    names.add("__future__")
    _STDLIB = names
    return names


def roots_for(runner_path):
    """The directories an import is resolved from, in the runner's own order.

    Python puts the running script's directory first; ``review_applied.py``
    adds the directory one level up so the shared ``scripts/`` modules resolve
    too. The path is set here explicitly rather than read from ``sys.path``,
    so a module installed elsewhere on the host cannot stand in for a module
    the install failed to copy in.
    """
    here = os.path.dirname(os.path.abspath(runner_path))
    return (here, os.path.dirname(here))


def module_file(name, roots):
    """The file an import of ``name`` would load from ``roots``, or None."""
    for root in roots:
        candidate = os.path.join(root, name + ".py")
        if os.path.isfile(candidate):
            return candidate
        package = os.path.join(root, name, "__init__.py")
        if os.path.isfile(package):
            return package
    return None


def imports_of(tree):
    """Top-level module names imported anywhere in ``tree``.

    Every import counts, not only the top-level ones: a module imported inside
    a function still has to be on disk. A relative import names a module in a
    package, not a file next to the runner, so it is skipped.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            found.append(node.module.split(".")[0])
    return found


def check(runner_path):
    """The modules this install cannot resolve, as [{module, importer, why}].

    Empty means the install is complete. ``importer`` is the file name that
    imports the missing module, or None when the module is loaded by path.
    """
    runner_path = os.path.abspath(runner_path)
    here = os.path.dirname(runner_path)
    roots = roots_for(runner_path)
    problems = []
    reported = set()
    queue = []

    def report(name, importer, why):
        if name in reported:
            return
        reported.add(name)
        problems.append({"module": name, "importer": importer, "why": why})

    if not os.path.isfile(runner_path):
        report(os.path.basename(runner_path), None, "the runner itself is missing")
        return problems
    queue.append((os.path.basename(runner_path)[:-3], runner_path, None))

    for name in LOADED_BY_PATH:
        path = os.path.join(here, name)
        if os.path.isfile(path):
            queue.append((name[:-3], path, None))
        else:
            report(name[:-3], None, "loaded by path, not present next to the runner")

    visited = set()
    while queue:
        name, path, importer = queue.pop(0)
        if path in visited:
            continue
        visited.add(path)
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
        except OSError as exc:
            report(name, importer, "cannot be read: %s" % exc)
            continue
        except (SyntaxError, ValueError) as exc:
            report(name, importer, "cannot be parsed: %s" % exc)
            continue
        for imported in imports_of(tree):
            target = module_file(imported, roots)
            if target is not None:
                queue.append((imported, target, os.path.basename(path)))
            elif imported not in _stdlib_names():
                report(imported, os.path.basename(path),
                       "not in the runner checkout and not in the stdlib")
    return problems


def report(problems, runner_path):
    """The loud lines a refusal writes, one string per line.

    Every line starts with ``local-ci:`` so the log reads as one event, and the
    first line says what happened and that the tick stopped.
    """
    if not problems:
        return []
    roots = roots_for(runner_path)
    lines = [
        "local-ci: install incomplete: %d module(s) the runner imports cannot be "
        "resolved; refusing to tick (DIG-5585)" % len(problems)
    ]
    for p in problems:
        imported_by = " (imported by %s)" % p["importer"] if p.get("importer") else ""
        lines.append(
            "local-ci:   missing module %s%s: %s; looked in %s"
            % (p["module"], imported_by, p["why"], " and ".join(roots))
        )
    lines.append(
        "local-ci: a missing import binds to None in this runner, so a tick would "
        "post a false verdict instead of a true one. Restore the module(s), then "
        "let the tick run again."
    )
    return lines


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    runner = argv[0] if argv else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "local_ci.py")
    problems = check(runner)
    if problems:
        for line in report(problems, runner):
            sys.stderr.write(line + "\n")
        return EXIT_CONFIG
    print("import_preflight: every module the runner imports resolves (%s)" % runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
