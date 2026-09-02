---
name: alt-data-sentiment-news-edit
description: Patch-update sentiment/news alt-data when triage signals localized change (edit mode).
---

# Sentiment & News Edit Skill — document_delta patch

Update an **existing** `alt-sentiment-news` document; do not rewrite from scratch.

## Output contract

Respond with **`DocumentPatch`** with `target_document_key`: `"alt-sentiment-news"`.
Patch paths: `/body`, `/internal_bias`, `/sources`, …

## Inputs

- `section_index` + `prior_document`, `triage_reason`, `web_grounding` when present

## Rules

- Patch only catalysts or sentiment scores that moved; append/remove list ops sparingly.
- Keep `retail_sentiment_stance` literals valid.
