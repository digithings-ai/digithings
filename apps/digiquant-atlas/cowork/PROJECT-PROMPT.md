# Paste into Claude Cowork — project instructions

Copy everything in the block below into your Cowork **project** system prompt (or project instructions field). Keep it short so task-specific prompts stay in each scheduled task.

---

**digiquant-atlas (workspace = this repo root)**

1. **Always read** `cowork/PROJECT.md` at the start of every session before doing work.
2. When a **scheduled task** runs, also read the task file named in that task’s instructions (under `cowork/tasks/`). Do not skip the task file.
3. **Canonical operations** live in `RUNBOOK.md` (publish, validate, schedules). **Agent behavior** in `AGENTS.md`. Follow them for anything not spelled out here.
4. **Supabase + JSON** are source of truth; markdown is derived. Do not recreate historical markdown-on-disk workflows.
5. **GitHub Actions** refresh prices/technicals/metrics into the **database** on a weekday schedule. When **Supabase MCP** is available, **read** that state from the DB (prices, technicals, portfolio tables) instead of guessing or relying on training data. **Writes:** use `scripts/publish_document.py` and `RUNBOOK.md` flows — local `data/agent-cache/` alone is not sufficient.
6. **Other MCP tools** you have enabled (e.g. FRED, Alpha Vantage, CoinGecko, SEC, fear & greed) are **optional** — use only when they help the specific research question; you are not required to call every tool. See `cowork/PROJECT.md` (MCP section) and `docs/ops/data-sources.md`.
7. Never invent live prices, yields, or numbers from model cutoff knowledge; use DB/MCP/search as appropriate.
8. **Cowork setup:** If the user asks to **set up**, **configure**, or **schedule** Atlas in Claude Cowork (project + tasks), follow **`cowork/SETUP-ATLAS-COWORK.md`** end-to-end: interview them for cadence/timezone/task pattern, update `config/schedule.json` → `cowork_operator`, write **`cowork/OPERATOR-COWORK.md`** with paste-ready project + task instructions, and give them the same blocks in chat.

---

*(End of paste block.)*
