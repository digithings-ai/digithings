# Cowork folder — Claude Cowork / scheduled agents

Use this directory when **Claude Cowork** (or any scheduler) runs against **this repository**.

| File | Role |
|------|------|
| [`PROJECT.md`](PROJECT.md) | **Project briefing** — read first every session; how the codebase works, env, tracks, links |
| [`PROJECT-PROMPT.md`](PROJECT-PROMPT.md) | **Short text to paste** into Cowork *project* settings (points the agent at `PROJECT.md` + tasks) |
| [`SETUP-ATLAS-COWORK.md`](SETUP-ATLAS-COWORK.md) | **Interactive setup wizard** for the agent: asks cadence/schedule, writes `OPERATOR-COWORK.md` + `cowork_operator` in `config/schedule.json`, emits paste-ready Cowork task text |
| [`OPERATOR-COWORK.example.md`](OPERATOR-COWORK.example.md) | Example of generated [`OPERATOR-COWORK.md`](OPERATOR-COWORK.md) (created by the setup flow; safe to commit your real copy) |
| [`tasks/`](tasks/) | **Task recipes** — each scheduled job should reference *one* task file as its instruction body |

Canonical operator detail stays in repo root [`RUNBOOK.md`](../RUNBOOK.md) and [`AGENTS.md`](../AGENTS.md). This folder **orients** the agent and **routes** to those docs—no duplicate maintenance of long procedures here.
