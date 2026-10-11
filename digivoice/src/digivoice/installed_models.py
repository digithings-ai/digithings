"""Local models already installed by LM Studio, Ollama, and MLX Studio.

Scans those apps' model directories. A missing app is an empty list.
Only files digivoice can run locally are returned: GGUF weights and
whisper.cpp ``.bin`` files. An Ollama tag whose blob is not on disk is
left out, because selecting it would pull from the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from digivoice.catalog import REWRITE_CATALOG, STT_CATALOG

Kind = Literal["stt", "rewrite"]
Source = Literal["lmstudio", "ollama", "mlxstudio"]
Finder = Callable[[Path], list[Path]]

_GGUF_MAGIC = b"GGUF"
_MODEL_LAYER = "application/vnd.ollama.image.model"
_SKIP_SUFFIXES = (
    ".safetensors",
    ".partial",
    ".tmp",
    ".download",
    ".onnx",
    ".json",
    ".md",
    ".txt",
)


class InstalledModel(BaseModel):
    """One runnable file found outside the digivoice models directory."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: str
    kind: Kind
    languages: str
    source: Source


def install_roots(home: Path, env: Mapping[str, str] | None = None) -> list[tuple[Source, Path]]:
    """macOS model directories for the three local apps. Order is stable."""
    table = env or {}
    ollama = table.get("OLLAMA_MODELS", "").strip()
    ollama_root = Path(ollama).expanduser() if ollama else home / ".ollama" / "models"
    return [
        ("lmstudio", home / ".lmstudio" / "models"),
        ("lmstudio", home / ".cache" / "lm-studio" / "models"),
        ("ollama", ollama_root),
        ("mlxstudio", home / ".mlxstudio" / "models"),
    ]


def default_finder(root: Path) -> list[Path]:
    """Files under ``root``. A missing directory is an empty list, not an error."""
    if not root.is_dir():
        return []
    found: list[Path] = []
    try:
        for path in root.rglob("*"):
            if path.is_file():
                found.append(path)
    except OSError:
        return []
    return found


def discover_installed_models(
    home: Path,
    env: Mapping[str, str] | None = None,
    *,
    finder: Finder | None = None,
) -> list[InstalledModel]:
    """Scan install roots. ``finder`` is injected in tests so the apps need not be present."""
    walk = finder or default_finder
    catalog_names = {item.filename.casefold() for item in (*STT_CATALOG, *REWRITE_CATALOG)}
    found: list[InstalledModel] = []
    seen: set[str] = set()
    for source, root in install_roots(home, env):
        try:
            files = walk(root)
        except OSError:
            continue
        if source == "ollama":
            found.extend(_from_ollama(root, files, catalog_names, seen))
        for path in files:
            item = _from_file(source, path, catalog_names, seen)
            if item is not None:
                found.append(item)
    return found


def _from_file(
    source: Source,
    path: Path,
    catalog_names: set[str],
    seen: set[str],
) -> InstalledModel | None:
    if _is_ollama_manifest(path) or _is_ollama_blob(path):
        return None
    name = path.name
    if name.casefold() in catalog_names or name.startswith("."):
        return None
    lower = name.casefold()
    if lower.endswith(_SKIP_SUFFIXES) or lower.endswith((".partial", ".download")):
        return None
    kind: Kind | None = None
    if lower.endswith(".gguf"):
        kind = "rewrite"
    elif lower.endswith(".bin") and ("ggml" in lower or "whisper" in lower):
        kind = "stt"
    if kind is None:
        return None
    resolved = _remember(path, seen)
    if resolved is None:
        return None
    languages = "en" if ".en" in lower else "multilingual"
    return InstalledModel(
        name=path.stem,
        path=resolved,
        kind=kind,
        languages=languages,
        source=source,
    )


def _from_ollama(
    root: Path,
    files: Sequence[Path],
    catalog_names: set[str],
    seen: set[str],
) -> list[InstalledModel]:
    items: list[InstalledModel] = []
    for path in files:
        if not _is_ollama_manifest(path):
            continue
        item = _ollama_manifest(root, path, catalog_names, seen)
        if item is not None:
            items.append(item)
    return items


def _is_ollama_manifest(path: Path) -> bool:
    return "manifests" in path.parts and path.is_file() and path.suffix.casefold() != ".json"


def _is_ollama_blob(path: Path) -> bool:
    return "blobs" in path.parts


def _ollama_manifest(
    root: Path,
    manifest: Path,
    catalog_names: set[str],
    seen: set[str],
) -> InstalledModel | None:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    layers = payload.get("layers")
    if not isinstance(layers, list):
        return None
    digest = ""
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        media = str(layer.get("mediaType", ""))
        if _MODEL_LAYER in media:
            digest = str(layer.get("digest", ""))
            break
    if not digest.startswith("sha256:"):
        return None
    blob = root / "blobs" / digest.replace(":", "-", 1)
    if not blob.is_file() or not _starts_with_gguf(blob):
        return None
    if blob.name.casefold() in catalog_names:
        return None
    resolved = _remember(blob, seen)
    if resolved is None:
        return None
    parts = manifest.parts
    name = manifest.parent.name
    if "library" in parts:
        index = parts.index("library")
        if index + 1 < len(parts) - 1:
            name = parts[index + 1]
    folded = name.casefold()
    languages = "en" if folded.endswith(".en") or ".en" in folded else "multilingual"
    return InstalledModel(
        name=name,
        path=resolved,
        kind="rewrite",
        languages=languages,
        source="ollama",
    )


def _starts_with_gguf(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == _GGUF_MAGIC
    except OSError:
        return False


def local_filenames(home: Path, env: Mapping[str, str] | None = None) -> set[str]:
    """Casefolded file names under install roots.

    A catalog row is already on disk when this set contains its filename,
    even if the models directory does not. A partial is not an installed file.
    """
    names: set[str] = set()
    for _source, root in install_roots(home, env):
        if not root.is_dir():
            continue
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                name = path.name
                if not name or name.startswith("."):
                    continue
                folded = name.casefold()
                if folded.endswith(".partial") or folded.endswith(".download"):
                    continue
                names.add(folded)
        except OSError:
            continue
    return names


def find_local_weight(
    home: Path,
    env: Mapping[str, str] | None,
    filename: str,
) -> Path | None:
    """Return a file with this name under an install root.

    The model list hides catalog filenames so the same weights are not shown
    twice. A take still has to open that copy when it is the one on disk.
    The match ignores case, because LM Studio, Ollama, and MLX keep the
    catalog name with whatever case the download used.
    """
    name = Path(filename).name
    if not name or name in {".", ".."} or name.startswith("."):
        return None
    needle = name.casefold()
    for _source, root in install_roots(home, env):
        if not root.is_dir():
            continue
        folded: Path | None = None
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.name == name:
                    return path
                if folded is None and path.name.casefold() == needle:
                    folded = path
        except OSError:
            continue
        if folded is not None:
            return folded
    return None


def _remember(path: Path, seen: set[str]) -> str | None:
    try:
        resolved = str(path.expanduser().resolve())
    except OSError:
        return None
    if resolved in seen:
        return None
    seen.add(resolved)
    return resolved


__all__ = [
    "find_local_weight",
    "InstalledModel",
    "default_finder",
    "discover_installed_models",
    "install_roots",
]
