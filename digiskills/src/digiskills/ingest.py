"""Local-filesystem corpus builder.

Walks a directory, reads text-like files (markdown, code, config), skips
binary files and common noise directories, and produces a
:class:`~digiskills.models.Corpus`. Zero extra dependencies beyond the core
library (pydantic + pyyaml) — no digisearch/digifetch import, so this is the
default builder for ``SkillSource(kind=LOCAL_PATH, ...)``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from digiskills.models import Corpus, SkillSource, SourceDocument, SourceKind

# Directories never worth ingesting — build artifacts, VCS internals, deps.
_IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        "htmlcov",
        ".turbo",
    }
)

# Extensions treated as text worth ingesting. Anything else is skipped as
# likely-binary (images, archives, compiled artifacts, lockfiles).
_TEXT_EXTENSIONS: dict[str, str] = {
    ".md": "text/markdown",
    ".mdx": "text/markdown",
    ".rst": "text/plain",
    ".txt": "text/plain",
    ".py": "text/x-python",
    ".ts": "text/x-typescript",
    ".tsx": "text/x-typescript",
    ".js": "text/javascript",
    ".jsx": "text/javascript",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
}

DEFAULT_MAX_FILES = 500
# ~2MB of text keeps a downstream synthesis prompt bounded without special-casing huge repos.
DEFAULT_MAX_TOTAL_CHARS = 2_000_000
DEFAULT_MAX_FILE_CHARS = 200_000


class LocalPathCorpusBuilder:
    """Builds a :class:`Corpus` by walking a local directory tree.

    Args:
        max_files: Stop after ingesting this many files.
        max_total_chars: Stop once the accumulated corpus reaches this many characters.
        max_file_chars: Truncate any single file's content to this many characters.
    """

    def __init__(
        self,
        *,
        max_files: int = DEFAULT_MAX_FILES,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
        max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
    ) -> None:
        self.max_files = max_files
        self.max_total_chars = max_total_chars
        self.max_file_chars = max_file_chars

    def build(self, source: SkillSource) -> Corpus:
        """Ingest ``source.local_path`` into a :class:`Corpus`.

        Raises:
            ValueError: ``source.kind`` is not ``LOCAL_PATH``.
            FileNotFoundError: ``source.local_path`` does not exist.
        """
        if source.kind is not SourceKind.LOCAL_PATH:
            raise ValueError(f"LocalPathCorpusBuilder requires kind=LOCAL_PATH, got {source.kind}")
        root = source.local_path
        assert root is not None  # enforced by SkillSource._check_kind_matches_payload
        if not root.exists():
            raise FileNotFoundError(f"source path does not exist: {root}")

        documents: list[SourceDocument] = []
        total_chars = 0
        truncated = False

        for path in sorted(self._iter_files(root)):
            if len(documents) >= self.max_files:
                truncated = True
                break
            content_type = _TEXT_EXTENSIONS.get(path.suffix.lower())
            if content_type is None:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not text.strip():
                continue
            if len(text) > self.max_file_chars:
                text = text[: self.max_file_chars]
                truncated = True
            remaining_budget = self.max_total_chars - total_chars
            if remaining_budget <= 0:
                truncated = True
                break
            if len(text) > remaining_budget:
                text = text[:remaining_budget]
                truncated = True

            relative = path if root.is_file() else path.relative_to(root)
            documents.append(
                SourceDocument(
                    origin=str(relative),
                    title=str(relative),
                    content=text,
                    content_type=content_type,
                )
            )
            total_chars += len(text)
            if total_chars >= self.max_total_chars:
                truncated = True
                break

        return Corpus(documents=documents, truncated=truncated)

    def _iter_files(self, root: Path) -> Iterator[Path]:
        if root.is_file():
            yield root
            return
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _IGNORED_DIR_NAMES for part in path.relative_to(root).parts[:-1]):
                continue
            yield path
