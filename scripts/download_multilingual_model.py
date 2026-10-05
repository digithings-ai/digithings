"""Fetch the pinned multilingual embedding weights (build-time / pre-warm only).

Downloads the Xenova pre-quantized ONNX snapshot used by
``MultilingualEmbedder`` (no torch export step — the repo ships the
quantized encoder as published), so runtime never touches the network:
the provider loads this directory via onnxruntime + tokenizers only.

Usage:
    python scripts/download_multilingual_model.py --out-dir /models/multilingual
    DIGISEARCH_MULTILINGUAL_MODEL_DIR=/models/multilingual python -m scripts.index_occ_tickets
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from digisearch.embedding.providers.multilingual import (
    MULTILINGUAL_DIMENSIONS,
    MULTILINGUAL_MODEL_FILE,
    MULTILINGUAL_MODEL_ID,
    MULTILINGUAL_TOKENIZER_FILE,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-id", default=os.environ.get("MULTILINGUAL_MODEL_ID", MULTILINGUAL_MODEL_ID)
    )
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("DIGISEARCH_MULTILINGUAL_MODEL_DIR", "/models/multilingual"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import snapshot_download

    snapshot_path = Path(
        snapshot_download(
            repo_id=args.model_id,
            allow_patterns=[MULTILINGUAL_MODEL_FILE, MULTILINGUAL_TOKENIZER_FILE],
            local_dir=str(out_dir),
        )
    )
    model_path = snapshot_path / MULTILINGUAL_MODEL_FILE
    tokenizer_path = snapshot_path / MULTILINGUAL_TOKENIZER_FILE
    missing = [str(p) for p in (model_path, tokenizer_path) if not p.is_file()]
    if missing:
        raise SystemExit(f"multilingual model download incomplete, missing: {missing}")
    print(f"multilingual weights ready in {snapshot_path} ({MULTILINGUAL_DIMENSIONS}-dim)")


if __name__ == "__main__":  # pragma: no cover
    main()
