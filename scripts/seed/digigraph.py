"""digigraph fixtures for the local stack (plan section 5).

MEASURED, and worth stating plainly because it constrains the deliverable:
at the tree this leaf was written against, `digigraph/src/digigraph` exposes
only `/health`, `/healthz`, `/test_llm`, `/files/{path}`, and three
`/threads/{thread_id}/{history,state,resume}` routes. There is **no ingest
or seed route**, and no SQLAlchemy `__tablename__` in the package, so a
digigraph "fixture" cannot be pushed into the service the way the R2 market
slice is. Writing one would mean inventing a route — out of scope for a
seeding leaf, and a decision that belongs to the digigraph owner.

So the digigraph fixtures are emitted as deterministic files under
`scripts/seed/data/digigraph/`, which is what a local stack can actually
consume (the same corpus the digisearch ingester reads, plus per-thread
state that `/threads/{id}/state` will echo once the local adapter is
wired). `load_status()` reports the measured absence instead of pretending
the push happened.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.seed.deterministic import DEFAULT_SEED, digest, rng_for, stable_uuid

DATA_DIR = Path(__file__).resolve().parent / "data" / "digigraph"

#: Routes measured present in `digigraph/src/digigraph` at this leaf's base.
MEASURED_ROUTES = (
    "/health",
    "/healthz",
    "/test_llm",
    "/files/{path}",
    "/threads/{thread_id}/state",
)

THREADS: tuple[str, ...] = ("seed-thread-brief", "seed-thread-desk")


def thread_fixtures(*, seed: int = DEFAULT_SEED) -> list[tuple[Path, str]]:
    """Write one deterministic thread-state fixture per thread; return ``(path, sha256)``."""
    out: list[tuple[Path, str]] = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for index, thread_id in enumerate(THREADS):
        rng = rng_for(seed, "digigraph-thread", thread_id)
        payload = {
            "thread_id": thread_id,
            "synthetic": True,
            "seed": seed,
            "state_id": stable_uuid("digigraph-state", seed, thread_id),
            "turns": [
                {
                    "index": n,
                    "role": "user" if n % 2 == 0 else "assistant",
                    "content": (
                        f"Synthetic {thread_id} turn {n}. Deterministic from "
                        f"--seed {seed} (draw {rng.randrange(10000)})."
                    ),
                }
                for n in range(4)
            ],
        }
        path = DATA_DIR / f"{thread_id}.json"
        body = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        path.write_text(body, encoding="utf-8")
        out.append((path, digest(body)))
    return out


def load_status() -> dict[str, Any]:
    """Report the measured ingest surface, so the caller never claims a push."""
    return {
        "digigraph_ingest_route": None,
        "measured_routes": list(MEASURED_ROUTES),
        "reason": (
            "digigraph exposes no ingest/seed route at this tree; fixtures are "
            "emitted as files under scripts/seed/data/digigraph/ and are not "
            "pushed into the service"
        ),
    }
