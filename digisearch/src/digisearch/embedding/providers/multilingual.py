"""Small multilingual embedding provider for ticket search (#4756).

Wraps the Xenova ONNX port of ``paraphrase-multilingual-MiniLM-L12-v2``
(384-dim, 50+ languages) with mean-pooling plus L2 normalization, so an
English query can match German/Spanish ticket text. Runs on CPU via
``onnxruntime`` + ``tokenizers`` — no torch, no third-party API, no ticket
PII leaving the process.

Install: ``pip install digisearch[embedding-multilingual]``.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from digisearch.embedding.base import EmbeddingProvider

#: Pinned model id; recorded in vector metadata so an index cannot mix models.
MULTILINGUAL_MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"

#: 384-dim output width (matches occ_help MiniLM width by coincidence, but this
#: is a separate model — never mix collections; Chroma metadata guards that).
MULTILINGUAL_DIMENSIONS = 384

#: Logical migration version (`embedding_version`); bump when weights change.
MULTILINGUAL_VERSION = "1"

#: Files fetched from the HF repo (quantized ONNX keeps CPU inference small).
MULTILINGUAL_MODEL_FILE = "onnx/model_quantized.onnx"
MULTILINGUAL_TOKENIZER_FILE = "tokenizer.json"

#: Per-text token cap; longer texts truncate (documented demo-index tradeoff).
MULTILINGUAL_MAX_TOKENS = 256

EmbedFn = Callable[[list[str]], list[list[float]]]

_default_multilingual_singleton: MultilingualEmbedder | None = None
_default_multilingual_lock = threading.Lock()


def _missing_dep_error() -> RuntimeError:
    return RuntimeError(
        "multilingual embeddings need the 'embedding-multilingual' extra "
        "(onnxruntime, tokenizers, huggingface_hub); "
        "install with: pip install digisearch[embedding-multilingual]"
    )


class MultilingualEmbedder(EmbeddingProvider):
    """Paraphrase-multilingual-MiniLM-L12-v2 (384-dim) via local quantized ONNX."""

    #: Persisted on Chroma collection metadata (`embedding_model_id`).
    model_id: str = MULTILINGUAL_MODEL_ID
    #: Logical migration version (`embedding_version`); bump when weights change.
    version: str = MULTILINGUAL_VERSION

    def __init__(
        self,
        embed_fn: EmbedFn | None = None,
        model_dir: str | Path | None = None,
        max_tokens: int = MULTILINGUAL_MAX_TOKENS,
    ) -> None:
        self._embed_fn = embed_fn
        self._model_dir = Path(model_dir) if model_dir is not None else None
        self._max_tokens = max(1, int(max_tokens))
        self._session: object | None = None
        self._tokenizer: object | None = None
        self._load_lock = threading.Lock()

    @property
    def dimensions(self) -> int:
        return MULTILINGUAL_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._embed_fn is not None:
            return [[float(x) for x in vector] for vector in self._embed_fn(list(texts))]
        return self._embed_onnx(list(texts))

    def _resolve_files(self) -> tuple[Path, Path]:
        """Return (model_path, tokenizer_path), downloading once when needed."""
        if self._model_dir is not None:
            model_path = self._model_dir / MULTILINGUAL_MODEL_FILE
            tokenizer_path = self._model_dir / MULTILINGUAL_TOKENIZER_FILE
            if self._model_dir.suffix == ".onnx" or self._model_dir.is_file():
                model_path = self._model_dir
                tokenizer_path = self._model_dir.parent / MULTILINGUAL_TOKENIZER_FILE
            missing = [str(p) for p in (model_path, tokenizer_path) if not p.is_file()]
            if missing:
                raise RuntimeError(f"multilingual model files missing: {missing}")
            return model_path, tokenizer_path
        override = os.environ.get("DIGISEARCH_MULTILINGUAL_MODEL_DIR", "").strip()
        if override:
            return self._resolve_under(Path(override))
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            raise _missing_dep_error() from None
        cache = Path(
            snapshot_download(
                repo_id=MULTILINGUAL_MODEL_ID,
                allow_patterns=[MULTILINGUAL_MODEL_FILE, MULTILINGUAL_TOKENIZER_FILE],
            )
        )
        return cache / MULTILINGUAL_MODEL_FILE, cache / MULTILINGUAL_TOKENIZER_FILE

    def _resolve_under(self, root: Path) -> tuple[Path, Path]:
        model_path = root / MULTILINGUAL_MODEL_FILE
        tokenizer_path = root / MULTILINGUAL_TOKENIZER_FILE
        if root.is_file():
            model_path = root
            tokenizer_path = root.parent / MULTILINGUAL_TOKENIZER_FILE
        missing = [str(p) for p in (model_path, tokenizer_path) if not p.is_file()]
        if missing:
            raise RuntimeError(f"DIGISEARCH_MULTILINGUAL_MODEL_DIR has no model files: {missing}")
        return model_path, tokenizer_path

    def _load(self) -> tuple[object, object]:
        if self._session is not None and self._tokenizer is not None:
            return self._session, self._tokenizer
        with self._load_lock:
            if self._session is not None and self._tokenizer is not None:
                return self._session, self._tokenizer
            try:
                import onnxruntime
                from tokenizers import Tokenizer
            except ImportError:
                raise _missing_dep_error() from None
            model_path, tokenizer_path = self._resolve_files()
            session = onnxruntime.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
            tokenizer = Tokenizer.from_file(str(tokenizer_path))
            self._session, self._tokenizer = session, tokenizer
            return session, tokenizer

    def _embed_onnx(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        session, tokenizer = self._load()
        encodings = tokenizer.encode_batch(list(texts))
        cap = self._max_tokens
        ids: list[list[int]] = []
        masks: list[list[int]] = []
        type_ids: list[list[int]] = []
        width = 1
        for encoding in encodings:
            token_ids = list(encoding.ids)[:cap]
            attention = list(encoding.attention_mask)[:cap]
            kinds = list(encoding.type_ids)[:cap] if encoding.type_ids else [0] * len(token_ids)
            width = max(width, len(token_ids))
            ids.append(token_ids)
            masks.append(attention)
            type_ids.append(kinds)
        pad_id = 0
        try:
            candidate = tokenizer.token_to_id("[PAD]")
            if candidate is not None:
                pad_id = int(candidate)
        except Exception:
            pad_id = 0
        feed_ids = np.array([[*row, *[pad_id] * (width - len(row))] for row in ids], dtype=np.int64)
        feed_mask = np.array([[*row, *[0] * (width - len(row))] for row in masks], dtype=np.int64)
        feed_types = np.array(
            [[*row, *[0] * (width - len(row))] for row in type_ids], dtype=np.int64
        )
        names = [entry.name for entry in session.get_inputs()]
        feed: dict[str, object] = {}
        for name, values in (
            ("input_ids", feed_ids),
            ("token_type_ids", feed_types),
            ("attention_mask", feed_mask),
        ):
            if name in names:
                feed[name] = values
        if len(feed) < len(names):
            ordered = [feed_ids, feed_types, feed_mask]
            feed = {name: ordered[index] for index, name in enumerate(names[:3])}
        outputs = session.run(None, feed)
        hidden = np.asarray(outputs[0], dtype=float)
        weights = feed_mask.astype(float)[..., None]
        summed = (hidden * weights).sum(axis=1)
        counts = weights.sum(axis=1).clip(min=1.0)
        pooled = summed / counts
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return [[float(x) for x in row] for row in (pooled / norms).tolist()]


def get_default_multilingual_embedder() -> MultilingualEmbedder:
    """Process-wide multilingual default shared by construction sites."""
    global _default_multilingual_singleton
    if _default_multilingual_singleton is None:
        with _default_multilingual_lock:
            if _default_multilingual_singleton is None:
                _default_multilingual_singleton = MultilingualEmbedder()
    return _default_multilingual_singleton
