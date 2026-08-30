# GitHub Models — **retired 2026-07-30**

> **Status:** The GitHub Models platform (playground, model catalog, inference API,
> and BYOK endpoints) was **fully retired on 2026-07-30**. Do not add new
> dependencies. This page is kept as a tombstone so old links and agent memory do
> not reintroduce the provider.

**Historical free tier:** eval/prototyping only (never production). Rate limits
varied by Copilot tier. Access required a PAT with explicit `models:read`.

## Migration

| Was using GitHub Models for… | Prefer now |
|---|---|
| Free eval / Actions smoke | Groq, Gemini Flash, or Cerebras (see [../LLM_PROVIDERS.md](../LLM_PROVIDERS.md)) |
| GitHub-native PR review | GitHub Copilot |
| Azure-backed production | [Microsoft Foundry](https://learn.microsoft.com/azure/ai-foundry) |

There is **no** LiteLLM `github/…` entry in digithings `config/` anymore. If you
still have `GITHUB_TOKEN` / `github/…` model lines in a local override, delete them.

## Historical setup (obsolete)

The former PAT + `https://models.github.ai/inference/chat/completions` flow no
longer works after the retirement cutover. Brownouts ran 2026-07-16 and
2026-07-23; new orgs were blocked from 2026-06-16.

## Docs / provenance

- Snapshot: [`snapshots/github_models.yaml`](snapshots/github_models.yaml)
  (notes the 2026-07-30 retirement)
- Tracker: [#1589](https://github.com/digithings-ai/digithings/issues/1589)
- Changelog: https://github.blog/changelog/ (GitHub Models retirement)
