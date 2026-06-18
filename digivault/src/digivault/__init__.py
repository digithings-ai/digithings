"""DigiVault — Obsidian-style markdown vault management.

Core library: frontmatter parsing, wikilink parsing/rewriting, and the ``Vault``
index with backlinks, tags, and maintenance operations. Importing ``digivault``
pulls in only ``pydantic`` and ``pyyaml`` — never FastAPI. The HTTP service, MCP
server, and CLI live in ``digivault.server`` / ``digivault.mcp_server`` /
``digivault.cli`` and require the ``[service]`` extra.
"""

from __future__ import annotations

from digivault.frontmatter import dump_frontmatter, set_keys, split_frontmatter
from digivault.models import (
    LinkRef,
    LintReport,
    Note,
    ValidationIssue,
    VaultConfig,
)
from digivault.vault import Vault, VaultError
from digivault.wikilinks import parse_links, rewrite_target

__version__ = "0.1.0"

__all__ = [
    "Vault",
    "VaultError",
    "VaultConfig",
    "Note",
    "LinkRef",
    "LintReport",
    "ValidationIssue",
    "parse_links",
    "rewrite_target",
    "split_frontmatter",
    "dump_frontmatter",
    "set_keys",
    "__version__",
]
