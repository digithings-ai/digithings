"""digisearch seeds for the local stack (plan section 5).

The plan names `make seed-digisearch-local`, and that target already exists
(Makefile:189) and already works: this module does not reimplement it. It
supplies the two things that target needs and cannot invent for itself:

* the **corpus** — synthetic markdown dropped into `digisearch/seeds/`, the
  directory `scripts/seed_digisearch_local.py` reads;
* the **key** — the digisearch-scoped digikey key from
  :mod:`scripts.seed.digikey_keys`, passed through the environment so the
  raw secret never appears in an argv (argv is world-readable via `ps`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.seed.deterministic import DEFAULT_SEED, digest, rng_for

REPO_ROOT = Path(__file__).resolve().parents[2]
SEEDS_DIR = REPO_ROOT / "digisearch" / "seeds"
INGEST_SEED = Path(__file__).resolve().parent / "data" / "digisearch" / "local-stack-overview.md"


def corpus_documents(*, seed: int = DEFAULT_SEED) -> list[tuple[Path, str]]:
    """Materialise the synthetic corpus; return ``(path, sha256)`` per file.

    Writes are byte-stable: the same seed produces the same bytes, so a
    re-run does not show up as a corpus change in a diff.
    """
    out: list[tuple[Path, str]] = []
    topics = ("architecture", "tenancy", "data", "operations")
    for index, topic in enumerate(topics):
        path = SEEDS_DIR / f"seed-local-stack-{topic}.md"
        body = _document(topic=topic, seed=seed, index=index)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        out.append((path, digest(body)))
    if INGEST_SEED.exists():
        out.append((INGEST_SEED, digest(INGEST_SEED.read_text(encoding="utf-8"))))
    return out


def _document(*, topic: str, seed: int, index: int) -> str:
    rng = rng_for(seed, "digisearch-doc", topic)
    bullets = "\n".join(
        f"- {topic} note {n}: deterministic sample line {rng.randrange(1000, 9999)}"
        for n in range(1, 6)
    )
    return (
        f"# Seed corpus — {topic}\n\n"
        "Synthetic document for the digithings local reference stack. It carries no\n"
        "client data and no market data; every number is generated from `--seed`.\n\n"
        f"## Notes\n\n{bullets}\n\n"
        f"<!-- seed: {seed} | topic-index: {index} -->\n"
    )


def run_ingest(
    *,
    api_key: str,
    digisearch_url: str,
    digikey_url: str,
    index: str = "default",
    seeds_dir: Path | None = None,
    runner=subprocess.run,
) -> int:
    """Invoke the existing `make seed-digisearch-local` script with *api_key*.

    The key goes through the environment (``DIGISEARCH_SEED_API_KEY``),
    never the argv. Returns the child's exit code.
    """
    env = dict(os.environ)
    env.update(
        {
            "DIGISEARCH_SEED_API_KEY": api_key,
            "DIGISEARCH_URL": digisearch_url,
            "DIGIKEY_URL": digikey_url,
            "DIGISEARCH_INDEX": index,
        }
    )
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "seed_digisearch_local.py"),
        "--seeds-dir",
        str(seeds_dir or SEEDS_DIR),
        "--index",
        index,
    ]
    result = runner(cmd, env=env, cwd=str(REPO_ROOT), check=False)
    return int(result.returncode)
