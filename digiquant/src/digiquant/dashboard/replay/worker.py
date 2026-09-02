"""WP10.4 — spawn-isolated portfolio replay worker (#2784).

Parent process never constructs a Nautilus engine. Each arm runs in a fresh
``spawn`` child with JSON request/result I/O. Child failure is typed
inconclusive — never a fabricated portfolio fallback.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
import traceback
from decimal import Decimal
from pathlib import Path

from digiquant.dashboard.replay.models import (
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    inconclusive_result,
)

# Never fork — Nautilus / Rust logging requires a clean interpreter (#1389).
_SPAWN_CTX = multiprocessing.get_context("spawn")

DEFAULT_TIMEOUT_S = 120.0


def run_portfolio_replay_isolated(
    request: PortfolioReplayRequest,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    work_dir: Path | str | None = None,
) -> PortfolioReplayResult:
    """Spawn a fresh worker, run shared-cash replay, return a typed result."""
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    base = Path(work_dir) if work_dir is not None else Path(os.environ.get("TMPDIR", "/tmp"))
    base.mkdir(parents=True, exist_ok=True)
    req_path = base / f"portfolio-replay-{request.request_id}-request.json"
    res_path = base / f"portfolio-replay-{request.request_id}-result.json"
    if res_path.exists():
        res_path.unlink()

    req_path.write_text(
        json.dumps(request.model_dump(mode="json"), allow_nan=False),
        encoding="utf-8",
    )

    proc = _SPAWN_CTX.Process(
        target=_worker_entry,
        args=(str(req_path), str(res_path)),
        name=f"olympus-replay-{request.request_id}",
    )
    proc.start()
    proc.join(timeout=timeout_s)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5)
        return inconclusive_result(
            request_id=request.request_id,
            request_content_hash=request.content_hash(),
            status=PortfolioReplayStatus.TIMEOUT,
            message=f"worker exceeded timeout_s={timeout_s}",
            starting_cash=request.starting_cash,
        )

    exitcode = proc.exitcode
    if exitcode is None:
        return inconclusive_result(
            request_id=request.request_id,
            request_content_hash=request.content_hash(),
            status=PortfolioReplayStatus.CRASH,
            message="worker exited with unknown exit code",
            starting_cash=request.starting_cash,
        )
    if exitcode != 0:
        status = PortfolioReplayStatus.CRASH
        signal_note = ""
        if exitcode < 0:
            signal_note = f" (signal {-exitcode})"
            if exitcode == -6:
                signal_note = " (SIGABRT)"
        # Prefer child-written inconclusive JSON when present.
        loaded = _try_load_result(res_path)
        if loaded is not None and loaded.status != PortfolioReplayStatus.OK:
            return loaded
        return inconclusive_result(
            request_id=request.request_id,
            request_content_hash=request.content_hash(),
            status=status,
            message=f"worker crashed with exitcode={exitcode}{signal_note}",
            starting_cash=request.starting_cash,
        )

    loaded = _try_load_result(res_path)
    if loaded is None:
        return inconclusive_result(
            request_id=request.request_id,
            request_content_hash=request.content_hash(),
            status=PortfolioReplayStatus.INCONCLUSIVE,
            message="worker exited 0 but result JSON missing or invalid",
            starting_cash=request.starting_cash,
        )
    return loaded


def _try_load_result(path: Path) -> PortfolioReplayResult | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PortfolioReplayResult.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def _worker_entry(request_path: str, result_path: str) -> None:
    """Child process entry — load JSON, run one engine, write JSON."""
    req_path = Path(request_path)
    res_path = Path(result_path)
    request_id = "unknown"
    request_hash = "0" * 64
    starting_cash = Decimal("0")
    try:
        payload = json.loads(req_path.read_text(encoding="utf-8"))
        request = PortfolioReplayRequest.model_validate(payload)
        request_id = request.request_id
        request_hash = request.content_hash()
        starting_cash = request.starting_cash
        # Import inside the child so the parent never loads Nautilus.
        from digiquant.dashboard.replay.nautilus_portfolio import (
            run_shared_cash_portfolio_replay,
        )

        result = run_shared_cash_portfolio_replay(request)
        _write_result(res_path, result)
        if result.status != PortfolioReplayStatus.OK:
            # Non-ok but typed — exit 0 so parent reads the JSON status.
            return
    except Exception as exc:
        result = inconclusive_result(
            request_id=request_id,
            request_content_hash=request_hash,
            status=PortfolioReplayStatus.ERROR,
            message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            starting_cash=starting_cash,
        )
        try:
            _write_result(res_path, result)
        except OSError:
            sys.exit(2)
        # Typed error JSON written — exit 0 for parent to classify via status.
        return


def _write_result(path: Path, result: PortfolioReplayResult) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(result.model_dump(mode="json"), allow_nan=False),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m digiquant.dashboard.replay.worker --request X --result Y``."""
    parser = argparse.ArgumentParser(description="Olympus shared-cash portfolio replay worker")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    _worker_entry(str(args.request), str(args.result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "main",
    "run_portfolio_replay_isolated",
]
