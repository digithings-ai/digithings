"""Suggested local models for STT and post-process rewrite.

Setup lists these, then download + wire into the models directory. Files stay
on this machine — no cloud, URL, or user-hosted OpenAI-style endpoints.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.request import urlopen

from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL
from digivoice.settings import LOCAL_REWRITE_MODEL_FILE

Kind = Literal["stt", "rewrite"]
ProgressFn = Callable[[int, int | None], None]
FetchFn = Callable[..., None]

WHISPER_CPP_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    filename: str
    kind: Kind
    url: str
    title: str
    best_for: str
    languages: str
    size_hint: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "filename": self.filename,
            "kind": self.kind,
            "url": self.url,
            "title": self.title,
            "best_for": self.best_for,
            "languages": self.languages,
            "size_hint": self.size_hint,
        }


def _whisper(
    model_id: str, title: str, best_for: str, languages: str, size_hint: str
) -> CatalogModel:
    filename = f"{model_id}.bin"
    return CatalogModel(
        id=model_id,
        filename=filename,
        kind="stt",
        url=f"{WHISPER_CPP_BASE}/{filename}",
        title=title,
        best_for=best_for,
        languages=languages,
        size_hint=size_hint,
    )


STT_CATALOG: tuple[CatalogModel, ...] = (
    _whisper("ggml-tiny.en", "Tiny English", "lowest latency / low-power", "en", "~75 MB"),
    _whisper(
        "ggml-base.en",
        "Base English (default)",
        "everyday dictation (default)",
        "en",
        "~142 MB",
    ),
    _whisper(
        "ggml-small.en",
        "Small English",
        "higher accuracy when you can wait",
        "en",
        "~466 MB",
    ),
    _whisper(
        "ggml-tiny",
        "Tiny multilingual",
        "lowest latency, many languages",
        "multilingual",
        "~75 MB",
    ),
    _whisper(
        "ggml-base",
        "Base multilingual",
        "everyday dictation, many languages",
        "multilingual",
        "~142 MB",
    ),
    _whisper(
        "ggml-small",
        "Small multilingual",
        "higher accuracy, many languages",
        "multilingual",
        "~466 MB",
    ),
)

REWRITE_CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel(
        id="qwen2.5-0.5b-instruct-q4_k_m",
        filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
        kind="rewrite",
        url=(
            "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
            "qwen2.5-0.5b-instruct-q4_k_m.gguf"
        ),
        title="Qwen2.5 0.5B",
        best_for="fastest on-device rewrite",
        languages="multilingual",
        size_hint="~400 MB",
    ),
    CatalogModel(
        id="qwen2.5-1.5b-instruct-q4_k_m",
        filename=LOCAL_REWRITE_MODEL_FILE,
        kind="rewrite",
        url=(
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
            "qwen2.5-1.5b-instruct-q4_k_m.gguf"
        ),
        title="Qwen2.5 1.5B (default)",
        best_for="everyday rewrite (default)",
        languages="multilingual",
        size_hint="~1.1 GB",
    ),
    CatalogModel(
        id="qwen2.5-3b-instruct-q4_k_m",
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        kind="rewrite",
        url=(
            "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/"
            "qwen2.5-3b-instruct-q4_k_m.gguf"
        ),
        title="Qwen2.5 3B",
        best_for="stronger rewrite when you can wait",
        languages="multilingual",
        size_hint="~2.0 GB",
    ),
)


def stt_catalog() -> tuple[CatalogModel, ...]:
    return STT_CATALOG


def rewrite_catalog() -> tuple[CatalogModel, ...]:
    return REWRITE_CATALOG


def find_stt(model_id: str) -> CatalogModel | None:
    needle = model_id.strip()
    for item in STT_CATALOG:
        if item.id == needle or item.filename == needle:
            return item
    return None


def find_rewrite(model_id: str) -> CatalogModel | None:
    needle = model_id.strip()
    for item in REWRITE_CATALOG:
        if item.id == needle or item.filename == needle:
            return item
    return None


def stt_filename(model_id: str | None) -> str:
    raw = (model_id or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    found = find_stt(raw)
    if found:
        return found.filename
    name = Path(raw).name
    if name.endswith(".bin"):
        return name
    return f"{name}.bin"


def stt_language(model_id: str | None) -> str:
    raw = (model_id or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    found = find_stt(raw)
    if found:
        return "en" if found.languages == "en" else "auto"
    name = Path(raw).name.casefold()
    if name.endswith(".en.bin") or name.endswith(".en") or ".en." in name:
        return "en"
    return "auto"


def catalog_public() -> dict[str, Any]:
    return {
        "stt": [item.as_dict() for item in STT_CATALOG],
        "rewrite": [item.as_dict() for item in REWRITE_CATALOG],
    }


def _fetch_url(url: str, dest: Path, progress: ProgressFn | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urlopen(url, timeout=600) as response:
        total_raw = response.headers.get("Content-Length")
        total = int(total_raw) if total_raw and total_raw.isdigit() else None
        got = 0
        with tmp.open("wb") as handle:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                got += len(chunk)
                if progress is not None:
                    progress(got, total)
    tmp.replace(dest)


def _invoke_fetch(fetch: FetchFn, url: str, dest: Path, progress: ProgressFn | None) -> None:
    try:
        fetch(url, dest, progress=progress)
    except TypeError:
        fetch(url, dest)


def install_catalog_model(
    paths: VoicePaths,
    entry: CatalogModel,
    *,
    fetch: FetchFn | None = None,
    progress: ProgressFn | None = None,
) -> str:
    """Place `entry.filename` under models_dir. Idempotent. Local file only."""
    dest = Path(paths.models_dir) / Path(entry.filename).name
    if dest.is_file():
        return str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    worker = fetch or _fetch_url
    _invoke_fetch(worker, entry.url, dest, progress)
    if not dest.is_file():
        raise OSError(f"download did not write {dest}")
    return str(dest)


__all__ = [
    "REWRITE_CATALOG",
    "STT_CATALOG",
    "CatalogModel",
    "catalog_public",
    "find_rewrite",
    "find_stt",
    "install_catalog_model",
    "rewrite_catalog",
    "stt_catalog",
    "stt_filename",
    "stt_language",
]
