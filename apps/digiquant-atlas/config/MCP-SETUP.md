# Unified MCP + ingest secrets (single local file)

## Security

- **Never commit API keys.** If a key was pasted into chat, a ticket, or a screenshot, **rotate it** at the provider and create a new one.
- This repo ignores `config/mcp.secrets.env` and `config/supabase.env`. Only the **`.example`** templates are committed.

## One file for Python ingest + optional MCP env

1. Copy [`mcp.secrets.env.example`](mcp.secrets.env.example) → **`config/mcp.secrets.env`**.
2. Fill in values (same names as environment variables).
3. **Ingest scripts** (`ingest_fred.py`, etc.) load `config/supabase.env` then **`config/mcp.secrets.env`** automatically (via `scripts/lib/macro_ingest.py`).

So **`FRED_API_KEY`** lives once in `mcp.secrets.env` for local runs and matches the variable name expected by GitHub Actions (set the same value as a repo secret for CI).

## Cursor

- This repo commits **[`.cursor/mcp.json`](../.cursor/mcp.json)** (project MCP). It uses **`${env:VARIABLE_NAME}`** only — **no keys in git**.
- Cursor also reads **`~/.cursor/mcp.json`**; definitions are **merged**. Duplicate server names: prefer one location to avoid confusion.
- **`.vscode/` is gitignored** here; use **`.cursor/mcp.json`** as the shared team template.
- **Important:** Cursor only sees `${env:…}` if those variables exist when the app (or MCP host) starts. Practical options:
  - Launch Cursor from a terminal after:  
    `set -a && source /path/to/digiquant-atlas/config/mcp.secrets.env && set +a && cursor .`
  - Or use **[direnv](https://direnv.net/)** in the repo root to export `mcp.secrets.env` when you `cd` into the project, then start Cursor from that shell.
  - Or merge OS-level env in your login shell (`~/.zshrc`) — least portable.

If `${env:…}` is empty in your Cursor build, fall back to Cursor’s **password inputs** in the MCP UI for that server only.

## Claude Desktop (macOS)

- Typical path: `~/Library/Application Support/Claude/claude_desktop_config.json` with a top-level **`mcpServers`** object.
- Use [`mcp.claude-desktop.fragment.json`](mcp.claude-desktop.fragment.json) as a **merge** into your existing `mcpServers` (do not overwrite unrelated servers).
- Claude may or may not expand `${env:…}` the same way as Cursor; if not, use the same **export-before-launch** pattern or hardcode only in a **local** JSON that is never committed.

## Command paths

Templates use `uvx` and `npx` on your `PATH`. On macOS Homebrew, ensure GUI apps see your PATH (or use absolute paths like `/opt/homebrew/bin/uvx` in your **local** copy only).

## Related

- [RUNBOOK.md](../RUNBOOK.md) — `FRED_API_KEY` for GitHub Actions.
- [docs/ops/data-sources.md](../docs/ops/data-sources.md) — data sources and ingest scripts.
