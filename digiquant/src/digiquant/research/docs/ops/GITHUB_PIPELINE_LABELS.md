# GitHub labels for pipeline evolution / post-mortem

Create these **once** in the repository (UI: **Settings → Labels**) or with [`gh label create`](https://cli.github.com/manual/gh_label_create).

Suggested colors are arbitrary; adjust to match your theme.

| Label | Purpose |
|-------|---------|
| `evolution` | All items from the pipeline review / backlog system |
| `source/post-mortem` | Created from `scripts/pipeline_review_to_github.py` or manual post-mortem |
| `track/research` | Finding originated after Track A |
| `track/portfolio` | Finding originated after Track B |
| `type/validation` | Schema / `validate_*` failures |
| `type/semantic` | Content quality / depth / consistency |
| `type/prompt-task` | Cowork task / skill / agent instruction change |
| `type/script` | Python/shell automation |
| `severity/blocking` | Run failed or publish blocked |
| `severity/warn` | Non-blocking issue |
| `severity/info` | Informational |

## One-shot bootstrap (CLI)

From repo root, with `gh` authenticated:

```bash
gh label create evolution --color "5319E7" --description "Pipeline evolution backlog" 2>/dev/null || true
gh label create "source/post-mortem" --color "C5DEF5" --description "From pipeline_review sync" 2>/dev/null || true
gh label create "track/research" --color "0E8A16" --description "Track A" 2>/dev/null || true
gh label create "track/portfolio" --color "BFDADC" --description "Track B" 2>/dev/null || true
gh label create "type/validation" --color "D93F0B" --description "Schema or validator" 2>/dev/null || true
gh label create "type/semantic" --color "FBCA04" --description "Content or narrative quality" 2>/dev/null || true
gh label create "type/prompt-task" --color "C2E0C6" --description "Prompts, tasks, skills" 2>/dev/null || true
gh label create "type/script" --color "1D76DB" --description "Scripts and automation" 2>/dev/null || true
gh label create "severity/blocking" --color "B60205" --description "Blocked run" 2>/dev/null || true
gh label create "severity/warn" --color "F9D0C4" --description "Non-blocking" 2>/dev/null || true
gh label create "severity/info" --color "E4E669" --description "Informational" 2>/dev/null || true
```

`2>/dev/null || true` avoids failing if a label already exists.
