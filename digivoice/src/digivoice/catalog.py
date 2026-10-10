"""Suggested local models for STT, Piper voices, and post-process rewrite.

Setup lists these, then download + wire into the models directory. Files stay
on this machine — no cloud, URL, or user-hosted OpenAI-style endpoints.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.request import urlopen

from digivoice.models import VoicePaths
from digivoice.paths import DEFAULT_MODEL

Kind = Literal["stt", "rewrite", "voice"]
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
    sidecar_url: str = ""

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
    _whisper(
        "ggml-medium.en",
        "Medium",
        "clearer English when you can wait",
        "en",
        "~1.5 GB",
    ),
    _whisper(
        "ggml-medium",
        "Medium",
        "clearer dictation, many languages",
        "multilingual",
        "~1.5 GB",
    ),
    _whisper(
        "ggml-large-v3-turbo",
        "Large v3 turbo",
        "fast large model, many languages",
        "multilingual",
        "~1.6 GB",
    ),
    _whisper(
        "ggml-large-v3",
        "Large v3",
        "highest accuracy, many languages",
        "multilingual",
        "~3.1 GB",
    ),
)

#: digivoice/AGENTS.md-equivalent note: the rewrite catalog's model ids, filenames
#: and huggingface URLs live in ``config/digivoice-rewrite-models.json``, not here
#: (#5029 — no provider/model id as a string literal in production code). Edit that
#: file to add, remove or re-default a rewrite model.
_REWRITE_CATALOG_FILENAME = "digivoice-rewrite-models.json"


def _resolve_rewrite_catalog_path() -> Path:
    """Where the rewrite-model catalog lives: ``DIGI_CONFIG_PATH`` override, else repo ``config/``.

    Same convention as digigraph's ``model-policy.json`` resolution: this file is
    required, so resolution must not depend on the process's working directory.
    """
    override = os.environ.get("DIGI_CONFIG_PATH")
    if override:
        return Path(override) / _REWRITE_CATALOG_FILENAME
    return Path(__file__).resolve().parents[3] / "config" / _REWRITE_CATALOG_FILENAME


def _parse_rewrite_entry(raw: object) -> tuple[CatalogModel, bool]:
    """One ``models[]`` entry, or a raised ``ValueError`` when it is malformed."""
    if not isinstance(raw, Mapping):
        raise ValueError(f"rewrite model catalog entry is not an object: {raw!r}")
    try:
        model = CatalogModel(
            id=str(raw["id"]),
            filename=str(raw["filename"]),
            kind="rewrite",
            url=str(raw["url"]),
            title=str(raw["title"]),
            best_for=str(raw["best_for"]),
            languages=str(raw["languages"]),
            size_hint=str(raw["size_hint"]),
        )
    except KeyError as exc:
        raise ValueError(f"rewrite model catalog entry missing {exc}: {raw!r}") from exc
    return model, bool(raw.get("default", False))


def _load_rewrite_catalog(path: Path) -> tuple[tuple[CatalogModel, ...], CatalogModel]:
    """The rewrite catalog and its default entry, read from *path*.

    Fail-loud: this is what setup offers for the local rewrite model, so a missing,
    malformed, or mis-defaulted config file must not silently narrow or empty it
    (the opposite of a telemetry-only config, which can degrade to nothing).
    """
    if not path.is_file():
        raise FileNotFoundError(f"digivoice rewrite-model catalog not found at {path}")
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"digivoice rewrite-model catalog at {path} is not valid JSON: {exc}"
        ) from exc
    entries = raw.get("models") if isinstance(raw, Mapping) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"digivoice rewrite-model catalog at {path} declares no models")

    models: list[CatalogModel] = []
    default: CatalogModel | None = None
    for entry in entries:
        model, is_default = _parse_rewrite_entry(entry)
        models.append(model)
        if is_default:
            if default is not None:
                raise ValueError(
                    f"digivoice rewrite-model catalog at {path} marks more than one model default"
                )
            default = model
    if default is None:
        raise ValueError(f"digivoice rewrite-model catalog at {path} marks no model default")
    return tuple(models), default


REWRITE_CATALOG, _DEFAULT_REWRITE_MODEL = _load_rewrite_catalog(_resolve_rewrite_catalog_path())


def default_rewrite_model() -> CatalogModel:
    """The rewrite model setup preselects and downloads by default.

    Read from ``config/digivoice-rewrite-models.json`` at import time — the single
    source for what ``digivoice.settings.LOCAL_REWRITE_MODEL_FILE`` and
    ``digivoice.rewrite.LOCAL_REWRITE_MODEL_URL`` both resolve to.
    """
    return _DEFAULT_REWRITE_MODEL


def stt_model_path(models_dir: str | Path, model_id: str | None) -> Path:
    """File whisper-cli should open. An absolute local .bin is used as-is."""
    raw = (model_id or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if (
            candidate.is_absolute()
            and ".." not in candidate.parts
            and candidate.suffix.casefold() == ".bin"
        ):
            return candidate
    return Path(models_dir) / stt_filename(model_id)


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


_PIPER_VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def _piper(locale_path: str, filename: str, title: str) -> CatalogModel:
    url = f"{_PIPER_VOICE_BASE}/{locale_path}/{filename}"
    return CatalogModel(
        id=filename,
        filename=filename,
        kind="voice",
        url=url,
        title=title,
        best_for="local Piper voice",
        languages="en",
        size_hint="~60 MB",
        sidecar_url=f"{url}.json",
    )


VOICE_CATALOG: tuple[CatalogModel, ...] = (
    _piper("en/en_US/lessac/medium", "en_US-lessac-medium.onnx", "Lessac medium"),
    _piper("en/en_US/amy/medium", "en_US-amy-medium.onnx", "Amy medium"),
    _piper("en/en_GB/alba/medium", "en_GB-alba-medium.onnx", "Alba medium"),
)


def find_voice(name: str) -> CatalogModel | None:
    needle = Path(name.strip()).name
    if not needle:
        return None
    for item in VOICE_CATALOG:
        if item.id == needle or item.filename == needle:
            return item
    return None


def download_partial(dest: Path) -> Path:
    """Sibling written until the download finishes. Not a selected model file."""
    return dest.with_name(dest.name + ".partial")


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
    """Place `entry.filename` under models_dir. Idempotent. Local file only.

    Bytes land in a ``.partial`` sibling and replace the real file only after
    every piece is on disk. A failure deletes those partials and leaves every
    other model file alone.
    """
    dest = Path(paths.models_dir) / Path(entry.filename).name
    if dest.is_file():
        return str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    worker = fetch or _fetch_url
    pieces: list[tuple[str, Path]] = [(entry.url, dest)]
    if entry.sidecar_url:
        pieces.append((entry.sidecar_url, dest.with_name(dest.name + ".json")))
    partials = [download_partial(target) for _url, target in pieces]
    try:
        for (url, _target), partial in zip(pieces, partials, strict=True):
            _invoke_fetch(worker, url, partial, progress)
            if not partial.is_file():
                raise OSError(f"download did not write {dest}")
        for (_url, target), partial in zip(pieces, partials, strict=True):
            partial.replace(target)
    except Exception:
        for partial in partials:
            partial.unlink(missing_ok=True)
        raise
    return str(dest)


__all__ = [
    "REWRITE_CATALOG",
    "STT_CATALOG",
    "VOICE_CATALOG",
    "CatalogModel",
    "catalog_public",
    "default_rewrite_model",
    "download_partial",
    "find_rewrite",
    "find_stt",
    "find_voice",
    "install_catalog_model",
    "rewrite_catalog",
    "stt_catalog",
    "stt_filename",
    "stt_language",
    "stt_model_path",
]
