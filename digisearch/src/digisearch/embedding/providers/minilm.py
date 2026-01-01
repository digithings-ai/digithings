"""Local MiniLM embedding provider backed by direct ONNX runtime.

This uses the same all-MiniLM-L6-v2 ONNX archive Chroma downloads, with the same
tokenizer truncation/padding and mean-pooling, so vectors match the Chroma
backend's historical embedder. It does not import ``chromadb``: the public R0
image ships SQLite as the default and does not install the optional Chroma extra.
Install the model runtime with ``pip install digisearch[minilm]``.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import threading
from collections.abc import Callable
from pathlib import Path

from digisearch.embedding.base import EmbeddingProvider

#: Recorded in vector metadata so an index cannot silently mix embedding models.
MINILM_MODEL_ID = "all-MiniLM-L6-v2-384"

#: all-MiniLM-L6-v2 output width.
MINILM_DIMENSIONS = 384

#: Chroma's published ONNX archive and its pinned checksum.
MINILM_MODEL_URL = "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
MINILM_MODEL_SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
MINILM_MODEL_FILE = "model.onnx"
MINILM_TOKENIZER_FILE = "tokenizer.json"
MINILM_MAX_TOKENS = 256

EmbedFn = Callable[[list[str]], list[list[float]]]

_default_minilm_singleton: MiniLMEmbedder | None = None
_default_minilm_lock = threading.Lock()


def _missing_dep_error() -> RuntimeError:
    return RuntimeError(
        "minilm embeddings need the 'minilm' extra (onnxruntime, tokenizers); "
        "install with: pip install digisearch[minilm]"
    )


def _cache_root() -> Path:
    return Path.home() / ".cache" / "digisearch" / "onnx_models" / "all-MiniLM-L6-v2"


def _chroma_cache() -> Path:
    return Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx"


def _files_exist(directory: Path) -> bool:
    return (directory / MINILM_MODEL_FILE).is_file() and (
        directory / MINILM_TOKENIZER_FILE
    ).is_file()


def _download_model(root: Path) -> None:
    import httpx

    root.mkdir(parents=True, exist_ok=True)
    archive = root / "onnx.tar.gz"
    try:
        with httpx.stream(
            "GET", MINILM_MODEL_URL, follow_redirects=True, timeout=120.0
        ) as response:
            response.raise_for_status()
            with archive.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != MINILM_MODEL_SHA256:
            raise RuntimeError(
                f"minilm archive checksum mismatch: expected {MINILM_MODEL_SHA256}, got {digest}"
            )
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(root, filter="data")
    except Exception as exc:
        raise RuntimeError(f"minilm model download failed from {MINILM_MODEL_URL}: {exc}") from exc
    finally:
        archive.unlink(missing_ok=True)
    if not _files_exist(root / "onnx"):
        raise RuntimeError(
            f"minilm archive did not contain {MINILM_MODEL_FILE} and {MINILM_TOKENIZER_FILE}"
        )


class MiniLMEmbedder(EmbeddingProvider):
    """all-MiniLM-L6-v2 (384-dim) via the Chroma-compatible local ONNX model."""

    #: Persisted on Chroma collection metadata (`embedding_model_id`).
    model_id: str = MINILM_MODEL_ID
    #: Logical migration version (`embedding_version`); bump when weights change.
    version: str = "1"

    def __init__(
        self,
        embed_fn: EmbedFn | None = None,
        model_dir: str | Path | None = None,
        max_tokens: int = MINILM_MAX_TOKENS,
    ) -> None:
        self._embed_fn = embed_fn
        self._model_dir = Path(model_dir) if model_dir is not None else None
        self._max_tokens = max(1, int(max_tokens))
        self._session: object | None = None
        self._tokenizer: object | None = None
        self._load_lock = threading.Lock()

    def _fn(self) -> EmbedFn:
        """Return the configured embed function, or the local ONNX path.

        Kept as a method because tests and downstream callers patch it to inject
        a deterministic embedder without loading the model.
        """
        if self._embed_fn is not None:
            return self._embed_fn
        return self._embed_onnx

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(x) for x in vector] for vector in self._fn()(list(texts))]

    @property
    def dimensions(self) -> int:
        return MINILM_DIMENSIONS

    def _resolve_files(self) -> tuple[Path, Path]:
        if self._model_dir is not None:
            return self._resolve_under(self._model_dir)
        override = os.environ.get("DIGISEARCH_MINILM_MODEL_DIR", "").strip()
        if override:
            return self._resolve_under(Path(override))
        if _files_exist(_chroma_cache()):
            return _chroma_cache() / MINILM_MODEL_FILE, _chroma_cache() / MINILM_TOKENIZER_FILE
        root = _cache_root()
        if not _files_exist(root / "onnx"):
            _download_model(root)
        return root / "onnx" / MINILM_MODEL_FILE, root / "onnx" / MINILM_TOKENIZER_FILE

    def _resolve_under(self, root: Path) -> tuple[Path, Path]:
        if root.is_file():
            return root, root.parent / MINILM_TOKENIZER_FILE
        candidate = root / "onnx" if (root / "onnx").is_dir() else root
        model_path = candidate / MINILM_MODEL_FILE
        tokenizer_path = candidate / MINILM_TOKENIZER_FILE
        missing = [str(p) for p in (model_path, tokenizer_path) if not p.is_file()]
        if missing:
            raise RuntimeError(f"DIGISEARCH_MINILM_MODEL_DIR has no model files: {missing}")
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
            try:
                session = onnxruntime.InferenceSession(
                    str(model_path), providers=["CPUExecutionProvider"]
                )
                tokenizer = Tokenizer.from_file(str(tokenizer_path))
                tokenizer.enable_truncation(max_length=self._max_tokens)
                tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=self._max_tokens)
            except Exception as exc:
                raise RuntimeError(
                    f"minilm model load failed ({model_path}); set "
                    f"DIGISEARCH_MINILM_MODEL_DIR: {exc}"
                ) from exc
            self._session, self._tokenizer = session, tokenizer
            return session, tokenizer

    def _embed_onnx(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        session, tokenizer = self._load()
        encodings = tokenizer.encode_batch(list(texts))
        input_ids = np.array([encoding.ids for encoding in encodings], dtype=np.int64)
        attention_mask = np.array(
            [encoding.attention_mask for encoding in encodings], dtype=np.int64
        )
        token_type_ids = np.zeros_like(input_ids)
        outputs = session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        hidden = np.asarray(outputs[0], dtype=np.float32)
        mask = np.broadcast_to(np.expand_dims(attention_mask, -1), hidden.shape)
        pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1)
        norms[norms == 0.0] = 1e-12
        normalized = (pooled / norms[:, np.newaxis]).astype(np.float32)
        return [[float(x) for x in row] for row in normalized.tolist()]


def get_default_minilm_embedder() -> MiniLMEmbedder:
    """Process-wide MiniLM default shared by Chroma/Vectorize construction sites."""
    global _default_minilm_singleton
    if _default_minilm_singleton is None:
        with _default_minilm_lock:
            if _default_minilm_singleton is None:
                _default_minilm_singleton = MiniLMEmbedder()
    return _default_minilm_singleton
