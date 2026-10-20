"""Boot-path pins for the digithings-stack container entrypoint (#4156).

`entrypoint.sh` is PID 1 and ends in `exec /usr/bin/supervisord`, so any
unguarded command that fails under `set -eu` aborts the container: `:8000` never
opens and the Worker 503s every request (#4149). Every command before the `exec`
must therefore be either deliberately fail-fast or best-effort.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = (
    REPO_ROOT / "apps" / "digithings-stack-cloudflare" / "container" / "entrypoint.sh"
)
EXEC_LINE = "exec /usr/bin/supervisord"

# Commands whose failure is fatal on the boot path: they write to the filesystem
# and can fail on a read-only, full, or mispermissioned volume. Matched at the
# start of a command (not as a substring, so "zammad-mcp host" is not a `cp`).
RISKY = (
    "mkdir",
    "cp ",
    "mv ",
    "rm ",
    "install ",
    "dd ",
    "tee ",
    "truncate ",
    "sed ",
    "ln ",
    "chmod",
    "touch",
)
# Redirect targets that are not durable writes, so an unguarded `>`/`>>` to them
# is fine (e.g. `>/dev/null`).
_SAFE_REDIRECT_TARGETS = ("/dev/null",)


def _pre_exec_lines() -> list[str]:
    """Code lines before the final `exec`, with `\\` continuations joined.

    Joining matters: a guard placed on the continuation line (`cmd \\` then
    `|| echo WARN`) is invisible to a per-line scan otherwise. Full-line comments
    are dropped first, so prose mentioning the exec line is not mistaken for it.
    """
    code = [
        line for line in ENTRYPOINT.read_text().splitlines() if not line.lstrip().startswith("#")
    ]
    joined = "\n".join(code).replace("\\\n", " ")
    assert EXEC_LINE in joined, f"entrypoint no longer ends in `{EXEC_LINE}` — update this test"
    # Last occurrence: anything before the final exec is boot path.
    return [line.strip() for line in joined.rsplit(EXEC_LINE, 1)[0].splitlines() if line.strip()]


def _command_text(line: str) -> str:
    """The command a line runs, without `if !` / `command ` / an absolute path."""
    command = line.removeprefix("if ! ").removeprefix("command ").strip()
    if command.startswith("/"):
        command = command.rsplit("/", 1)[-1]
    return command


def _runs_risky_command(line: str) -> bool:
    return any(_command_text(line).startswith(token) for token in RISKY)


def _has_unguarded_write(line: str) -> bool:
    """The #4149 shape: a `>>` write to a durable path."""
    if ">>" not in line:
        return False
    target = line.split(">>", 1)[1].strip().split(" ", 1)[0]
    return target not in _SAFE_REDIRECT_TARGETS


def _is_condition(line: str) -> bool:
    """True for an `if`/`if !` condition, which `set -e` exempts.

    A failure there selects the `else` branch; it cannot abort the boot. The
    zammad alias relies on exactly that (`if printf … >> /etc/hosts; then … else
    echo WARN … fi`), which is why this is not an offender.
    """
    return line.startswith("if ") or line.startswith("if!")


def _boot_path_block(start_index: int) -> list[str]:
    """Lines from `start_index` through the block's closing `fi`."""
    block: list[str] = []
    for line in _pre_exec_lines()[start_index:]:
        block.append(line)
        if line == "fi":
            break
    return block


def _block_after(lines: list[str], needle: str) -> list[str]:
    """The `if` block whose opening line contains `needle`, up to its `fi`."""
    for index, line in enumerate(lines):
        if needle in line:
            block: list[str] = []
            for candidate in lines[index:]:
                block.append(candidate)
                if candidate == "fi":
                    return block
            return block
    raise AssertionError(f"no line contains {needle!r}")


def test_required_data_dirs_fail_fast_deliberately():
    """Creating the required dirs may abort the boot — but on purpose, legibly.

    Unlike the optional vault seed, the stack cannot serve without these, so
    fail-fast is the intended behaviour here; what is not acceptable is `set -e`
    killing PID 1 with a bare shell error.
    """
    lines = _pre_exec_lines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith("if !") and "mkdir -p" in line and "DATA_CHROMA" in line
    ]
    assert len(starts) == 1, f"expected exactly one required-dirs check, found {len(starts)}"
    block = _boot_path_block(starts[0])
    assert any("FATAL cannot create required data dirs" in line for line in block), block
    assert "exit 1" in block, f"required-dirs branch must exit non-zero: {block}"


def test_vault_seed_copies_are_best_effort():
    """A failed seed copy degrades the vault; it must not kill the container."""
    copies = [line for line in _pre_exec_lines() if line.startswith("cp ")]
    assert copies, "expected the vault seed copy commands"
    for line in copies:
        assert "||" in line, f"vault seed copy is unguarded: {line}"
        assert "digithings-stack: WARN" in line, f"vault seed copy guard must warn: {line}"


def test_vault_client_dir_creation_is_best_effort():
    mkdirs = [line for line in _pre_exec_lines() if "mkdir -p" in line and "clients" in line]
    assert mkdirs, "expected the vault client-dir mkdir"
    for line in mkdirs:
        assert "||" in line, f"vault client-dir mkdir is unguarded: {line}"
        assert "digithings-stack: WARN" in line, f"vault client-dir guard must warn: {line}"


def test_no_unguarded_risky_command_before_exec():
    """A floor on the boot-path class, not a proof.

    Conservative by construction: it matches a list of writing commands at line
    start (plus unguarded `>>` writes) and joins `\\` continuations. A fatal
    command spelled another way — a helper script, a pipe, a command inside a
    quoted program — slips through, so widen this rather than trusting it.
    """
    offenders = [
        line
        for line in _pre_exec_lines()
        if (_runs_risky_command(line) or _has_unguarded_write(line))
        and "||" not in line
        and not _is_condition(line)
    ]
    assert not offenders, "unguarded command(s) on the boot path: " + "; ".join(offenders)


def test_a_failing_cp_aborts_set_e_unless_guarded(tmp_path):
    """Pins the shell semantics the guards rely on, so the reasoning cannot rot."""
    missing = tmp_path / "no-such-dir" / "seed.md"
    dest = tmp_path / "dest.md"
    guarded = f"set -eu\ncp {missing} {dest} || echo WARN\necho REACHED\n"
    unguarded = f"set -eu\ncp {missing} {dest}\necho REACHED\n"
    ok = subprocess.run(["sh", "-c", guarded], capture_output=True, text=True)
    aborted = subprocess.run(["sh", "-c", unguarded], capture_output=True, text=True)
    assert ok.returncode == 0 and "REACHED" in ok.stdout
    assert aborted.returncode != 0 and "REACHED" not in aborted.stdout


def test_cheaperinference_merge_must_not_fall_back_silently():
    """A failed overlay merge must not be a SILENT fallback.

    The base file the image ships carries no curated model, so serving it
    quietly leaves LiteLLM answering every curated tenant model with
    model-not-found while the health probe stays green (DIG-4512). The
    fallback is allowed to exist, but it must name its verdict.
    """
    text = "\n".join(_pre_exec_lines())
    assert "merge failed; using default litellm.yaml" not in text, (
        "the silent merge fallback is still in the entrypoint"
    )
    assert "--require-curated-ids" in text, (
        "the merge must be told to check the curated ids"
    )


def test_cheaperinference_merge_failure_degrades_to_the_base_config():
    """A failed merge must NOT take the container down.

    The base config is a build-time COPY, so it is always present, and the
    container cold-starts on every request (ports.ts sleepAfter 1m): a boot
    abort would take digisearch, digivault and digikey down with it for every
    request after an idle minute. The failure therefore degrades to the base
    config and is named loudly in the log file (DIG-4512).
    """
    lines = _pre_exec_lines()
    block = _nested_if_block(lines, 'if [ -n "$_missing" ]')
    assert "exit 1" not in block, f"the merge failure branch must not abort: {block}"
    text = "\n".join(lines)
    assert "curated-models CHECK-FAILED - serving the base config" in text, (
        "the degraded path must name its verdict and the config it serves"
    )




def test_cheaperinference_missing_overlay_asset_degrades_to_the_base_config():
    """A missing overlay asset used to skip the whole merge block silently."""
    lines = _pre_exec_lines()
    block = _nested_if_block(lines, 'if [ -n "$_missing" ]')
    assert "exit 1" not in block, f"the missing-asset branch must not abort: {block}"
    assert "overlay asset missing" in "\n".join(block), block




def test_litellm_config_is_always_exported_for_supervisord():
    """supervisord expands %(ENV_LITELLM_CONFIG)s in the litellm command.

    An unset value expands to an empty --config, so litellm serves no model at
    all — the same silent outage the merge fallback caused (DIG-4512). Every
    LITELLM_CONFIG export must therefore be paired with an ENV_LITELLM_CONFIG
    export.
    """
    lines = _pre_exec_lines()
    exports = [
        (index, line)
        for index, line in enumerate(lines)
        if line.startswith("export LITELLM_CONFIG=")
    ]
    assert exports, "expected the LiteLLM config to be exported"
    for index, line in exports:
        following = lines[index + 1] if index + 1 < len(lines) else ""
        assert following.startswith("export ENV_LITELLM_CONFIG="), (
            f"LITELLM_CONFIG export is not paired with ENV_LITELLM_CONFIG: {line}"
        )


def _nested_if_span(lines: list[str], needle: str) -> tuple[int, int]:
    """The start and end index of the `if` block whose opening line has `needle`.

    The merge block nests `if`s, so the first `fi` after the opening line is
    not the end of the block.
    """
    start = next(index for index, line in enumerate(lines) if needle in line)
    depth = 0
    for index in range(start, len(lines)):
        line = lines[index]
        if line.startswith("if ") or line.startswith("if!"):
            depth += 1
        if line == "fi":
            depth -= 1
            if depth == 0:
                return start, index
    raise AssertionError(f"no matching `fi` for {needle!r}")


def _nested_if_block(lines: list[str], needle: str) -> list[str]:
    """The `if` block whose opening line contains `needle`, up to its MATCHING `fi`."""
    start, end = _nested_if_span(lines, needle)
    return lines[start:end + 1]


def test_a_failed_merge_degrades_to_the_base_config_and_keeps_booting(tmp_path):
    """The behaviour R1 asks for, run for real.

    A merge that fails must leave supervisord pointing at the base config,
    must not abort the boot, and must write the verdict - with the merge's
    own missing-model list - into the log file the operator reads.
    """
    lines = _pre_exec_lines()
    start = next(i for i, line in enumerate(lines) if "export LITELLM_CONFIG=" in line)
    _outer_start, outer_end = _nested_if_span(lines, 'if [ -n "$_ci_key" ]')
    block = lines[start:outer_end + 1]
    assert block[-1] == "fi", block[-1]

    app = tmp_path / "app"
    (app / "config").mkdir(parents=True)
    (app / "scripts").mkdir()
    for name in ("litellm.yaml", "litellm.cheaperinference.yaml"):
        (app / "config" / name).write_text("model_list: []\n")
    (app / "scripts" / "merge_litellm_cheaperinference.py").write_text("# stub\n")
    logs = tmp_path / "logs"
    logs.mkdir()
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "python3").write_text(
        "#!/bin/sh\necho 'ERROR: the merged litellm model_list is missing 1 curated"
        " model id(s): deepseek/deepseek-v4.1-flash' >&2\nexit 1\n"
    )
    (stub / "python3").chmod(0o755)

    body = "\n".join(block).replace("/app", str(app)).replace("/var/log/supervisor", str(logs))
    script = tmp_path / "boot.sh"
    script.write_text("set -eu\n" + body + '\necho "CFG=$ENV_LITELLM_CONFIG"\necho REACHED\n')
    env = dict(os.environ)
    env["PATH"] = str(stub) + ":" + env["PATH"]
    env["CHEAPERINFERENCE_API_KEY"] = "k"
    result = subprocess.run(["sh", str(script)], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "REACHED" in result.stdout, "the boot must continue past a failed merge"
    assert f"CFG={app}/config/litellm.yaml" in result.stdout, result.stdout
    verdict = (logs / "stack-entrypoint.log").read_text()
    assert "curated-models CHECK-FAILED" in verdict, verdict
    assert "deepseek/deepseek-v4.1-flash" in verdict, verdict


def _no_overlay_branch(lines: list[str]) -> list[str]:
    """The else branch of the OUTER cheaperinference merge block.

    The merge block nests `if`s and now has an inner `else` of its own, so
    the outer else has to be found by depth, not by being the first one.
    """
    outer_start, outer_end = _nested_if_span(lines, 'if [ -n "$_ci_key" ]')
    outer = lines[outer_start:outer_end + 1]
    depth = 0
    for index, line in enumerate(outer):
        if line.startswith("if ") or line.startswith("if!"):
            depth += 1
        elif line == "else" and depth == 1:
            branch: list[str] = []
            for candidate in outer[index:]:
                branch.append(candidate)
                if candidate == "fi":
                    return branch
            return branch
        if line == "fi":
            depth -= 1
    raise AssertionError("no else branch in the merge block")


def test_the_no_overlay_path_names_the_missing_curated_models():
    """The base config carries no curated model, so the gap must be named.

    Without the overlay the boot serves a model_list that answers every
    curated tenant model with model-not-found while /health stays green. The
    boot must say which ids are missing instead of logging one INFO line and
    continuing (DIG-4512).
    """
    text = "\n".join(_pre_exec_lines())
    assert "--check-config" in text, (
        "the boot must check the effective config for the curated ids"
    )
    assert "curated-models MISSING" in text, "the missing curated ids must be named"


def test_the_no_overlay_path_does_not_abort_the_boot():
    """A litellm-only fault must not take the whole stack down.

    The container cold-starts on every request (ports.ts sleepAfter 1m), so an
    abort on the no-overlay path would take digisearch, digivault and digikey
    down for every request after an idle minute. The merge branch still
    aborts: there the image is broken.
    """
    block = _no_overlay_branch(_pre_exec_lines())
    assert not any("exit 1" in line for line in block), block
    assert any("curated-models" in line for line in block), block


def test_loud_boot_lines_reach_the_operator_log_file():
    """The entrypoint's stderr is not captured by supervisord.

    supervisord only manages its own program logs, so a boot line that only
    reached stderr was invisible to every diagnostic except the container
    console. The loud lines must also reach a file in the supervisor log
    directory, where the operator looks for them (DIG-4512).
    """
    text = "\n".join(_pre_exec_lines())
    assert "stack-entrypoint.log" in text, (
        "the loud boot lines must also be written to a log file"
    )

