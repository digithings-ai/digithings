"""Bring-up orchestration for the local self-host stack.

Implements the command plans of ``dt up`` / ``dt down`` / ``dt seed`` /
``dt reset`` from the local-stack plan (section 3, steps 1-8) and is the only
part of that section that shells out.

Two of the plan's eight steps are *not* commands and are therefore NOT built
here; the caller (``scripts/dt``) owns them and this module says so:

* step 1, the preflight, is :mod:`scripts.localstack.preflight` (pure Python);
* step 8, the health gate plus the URL table, is :mod:`scripts.localstack.health`.

A step whose artefact belongs to another slice of the plan is **skipped, never
failed**: the sibling slices are still open pull requests, so their files are
absent from this tree.  Skipping is the honest report - reporting a failure
would say a decision was wrong when the file simply has not landed, and
reporting a pass would claim a capability that does not exist.  Each step names
the slice that owns the missing artefact so the gap is actionable.

Every command is overridable through a ``DT_*_CMD`` environment variable so a
host with different tool paths can drive the same plan.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"

#: Environment overrides, one per external command, whitespace separated.
COMMAND_ENV = {
    "secrets": "DT_SECRETS_CMD",
    "supabase": "DT_SUPABASE_CMD",
    "compose": "DT_COMPOSE_CMD",
    "wrangler": "DT_WRANGLER_CMD",
    "proxy": "DT_PROXY_CMD",
    "seed": "DT_SEED_CMD",
    "python": "DT_PYTHON_CMD",
}

COMMANDS = ("up", "down", "seed", "reset")


@dataclass(frozen=True)
class Step:
    """One external command in a bring-up plan.

    ``optional`` means a failure is reported but does not fail the plan, for a
    step whose surface is genuinely best-effort (the reverse proxy, a second
    seed pass).  It never means "ignore a real error in something that ran".

    ``requires`` lists repository-relative paths that must exist for the step to
    run at all.  When none of them is present the step is skipped with a reason
    naming the owning slice.
    """

    name: str
    argv: tuple[str, ...]
    optional: bool = False
    requires: tuple[str, ...] = ()
    note: str = ""
    owner: str = ""

    def missing(self, root: Path) -> tuple[str, ...]:
        """Repository-relative paths from ``requires`` that do not exist."""
        return tuple(p for p in self.requires if not (root / p).exists())


@dataclass(frozen=True)
class StepOutcome:
    """The measured result of one step."""

    name: str
    status: str
    detail: str
    argv: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "argv": list(self.argv),
        }


@dataclass(frozen=True)
class StepReport:
    """The measured result of a whole plan."""

    command: str
    outcomes: tuple[StepOutcome, ...] = ()
    dry_run: bool = False

    @property
    def failed(self) -> tuple[StepOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == FAILED)

    @property
    def skipped(self) -> tuple[StepOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == SKIPPED)

    @property
    def passed(self) -> tuple[StepOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == PASSED)

    @property
    def ok(self) -> bool:
        """True when nothing failed.  A skip never fails a plan."""
        return not self.failed

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "ok": self.ok,
            "dry_run": self.dry_run,
            "counts": {
                "passed": len(self.passed),
                "failed": len(self.failed),
                "skipped": len(self.skipped),
                "total": len(self.outcomes),
            },
            "steps": [o.to_dict() for o in self.outcomes],
        }


Runner = Callable[[Sequence[str], Path, Mapping[str, str]], "tuple[int, str]"]


def subprocess_runner(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> "tuple[int, str]":
    """Run ``argv`` in ``cwd``, returning ``(returncode, combined output)``."""
    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    except OSError as exc:  # pragma: no cover - defensive
        return 126, f"{type(exc).__name__}: {exc}"
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    return proc.returncode, output.strip()


def _tool(env: Mapping[str, str], key: str, default: Sequence[str]) -> tuple[str, ...]:
    """Resolve a command, honouring its ``DT_*_CMD`` override."""
    override = env.get(COMMAND_ENV[key])
    if override:
        return tuple(shlex.split(override))
    return tuple(default)


def plan_up(profile: str, env: Mapping[str, str]) -> tuple[Step, ...]:
    """Plan section 3, steps 2-7.  Steps 1 and 8 belong to the caller."""
    python = _tool(env, "python", ("python3",))
    secrets = (*_tool(env, "secrets", ("scripts/dt-secrets",)), "render")
    supabase = _tool(env, "supabase", ("supabase",))
    compose = _tool(env, "compose", ("docker", "compose"))
    wrangler = _tool(
        env, "wrangler", ("npx", "wrangler", "dev", "--local", "--persist-to", ".wrangler/state")
    )
    proxy = _tool(env, "proxy", ("caddy", "run", "--config", "infra/local-proxy/Caddyfile"))
    seed = (*python, "scripts/seed/seed_all.py")
    return (
        Step(
            "secrets-render",
            secrets,
            optional=True,
            requires=("scripts/dt-secrets",),
            note="renders .dev.vars / .env.local, mode 600, never echoes",
            owner="S5 (DIG-2773, PR #5360)",
        ),
        Step("supabase-start", (*supabase, "start"), note="plan step 3"),
        Step(
            "supabase-db-reset",
            (*supabase, "db", "reset"),
            note="replays digiquant/supabase/migrations then seed.sql",
        ),
        Step("compose-up", (*compose, "--profile", profile, "up", "-d"), note="plan step 4"),
        Step(
            "wrangler-dev",
            wrangler,
            note=(
                "one multi-config session so service bindings resolve; "
                "fixed ports so the health gate can address them"
            ),
            requires=("apps/dashboard-api/wrangler.toml",),
            owner="S3 (DIG-2771, PR #5353)",
        ),
        Step(
            "reverse-proxy",
            proxy,
            optional=True,
            requires=("infra/local-proxy/Caddyfile",),
            note="serves *.digithings.localhost",
            owner="S4 (DIG-2772, PR #5355)",
        ),
        Step(
            "seed",
            (*seed, "--seed"),
            optional=True,
            requires=("scripts/seed/seed_all.py",),
            note="deterministic synthetic data only",
            owner="S6 (DIG-2774, PR #5356)",
        ),
    )


def plan_down(profile: str, env: Mapping[str, str]) -> tuple[Step, ...]:
    """Stop everything ``dt up`` started, leaving data on disk."""
    supabase = _tool(env, "supabase", ("supabase",))
    compose = _tool(env, "compose", ("docker", "compose"))
    return (
        Step(
            "compose-down",
            (*compose, "--profile", profile, "down", "--remove-orphans"),
            note="volumes are kept; dt reset is the destructive path",
        ),
        Step("supabase-stop", (*supabase, "stop"), optional=True, note="plan step 3 teardown"),
        Step(
            "stop-legacy-stack",
            ("scripts/stop_stack_local.sh",),
            optional=True,
            note="pre-existing no-container launcher; not the containerised stack",
        ),
    )


def plan_seed(env: Mapping[str, str], seed: str = "42") -> tuple[Step, ...]:
    """Seed synthetic data on an already-running stack."""
    python = _tool(env, "python", ("python3",))
    return (
        Step(
            "seed-all",
            (*python, "scripts/seed/seed_all.py", "--seed", seed),
            requires=("scripts/seed/seed_all.py",),
            note="deterministic, idempotent, synthetic only",
            owner="S6 (DIG-2774, PR #5356)",
        ),
    )


def plan_reset(env: Mapping[str, str], seed: str = "42") -> tuple[Step, ...]:
    """Destructive path: reload the local database from migrations, then seed."""
    supabase = _tool(env, "supabase", ("supabase",))
    return (
        Step(
            "supabase-db-reset",
            (*supabase, "db", "reset"),
            note="DESTRUCTIVE: drops and rebuilds the local database",
        ),
        *plan_seed(env, seed),
    )


def steps_for(
    command: str,
    profile: str,
    env: Mapping[str, str],
    seed: str = "42",
) -> tuple[Step, ...]:
    """Dispatch a CLI command name to its plan."""
    if command == "up":
        return plan_up(profile, env)
    if command == "down":
        return plan_down(profile, env)
    if command == "seed":
        return plan_seed(env, seed)
    if command == "reset":
        return plan_reset(env, seed)
    raise ValueError(f"unknown command {command!r}; expected one of {', '.join(COMMANDS)}")


def run_step(
    step: Step,
    root: Path,
    env: Mapping[str, str],
    dry_run: bool = False,
    runner: Runner = subprocess_runner,
) -> StepOutcome:
    """Run one step, or explain precisely why it did not run."""
    missing = step.missing(root)
    if step.requires and len(missing) == len(step.requires):
        owner = f" (owned by {step.owner})" if step.owner else ""
        return StepOutcome(
            step.name,
            SKIPPED,
            f"artefact not present: {', '.join(missing)}{owner}",
            step.argv,
        )
    if dry_run:
        return StepOutcome(
            step.name,
            SKIPPED,
            f"dry-run: {' '.join(step.argv)}",
            step.argv,
        )
    code, output = runner(step.argv, root, env)
    tail = output.strip().splitlines()[-1] if output.strip() else "no output"
    return StepOutcome(
        step.name,
        PASSED if code == 0 else FAILED,
        f"exit {code}: {tail}",
        step.argv,
    )


def run_steps(
    command: str,
    steps: Sequence[Step],
    root: Path,
    env: Mapping[str, str],
    dry_run: bool = False,
    runner: Runner = subprocess_runner,
) -> StepReport:
    """Run a whole plan in order.

    A failed step stops the plan: later steps assume the earlier ones ran, so
    continuing would report a cascade of failures for one cause.
    """
    outcomes: list[StepOutcome] = []
    for step in steps:
        outcome = run_step(step, root, env, dry_run=dry_run, runner=runner)
        outcomes.append(outcome)
        if outcome.status == FAILED and not step.optional:
            break
    return StepReport(command=command, outcomes=tuple(outcomes), dry_run=dry_run)


def step_rows(report: StepReport) -> tuple[tuple[str, ...], ...]:
    """Table rows for the console renderer."""
    return tuple((o.name, o.status.upper()[:4], o.detail) for o in report.outcomes)
