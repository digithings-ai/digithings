---
name: Pipeline improvement
description: Track a fix or enhancement identified from a pipeline post-mortem (`pipeline_review`) or manual triage.
title: "[pipeline] "
labels:
  - evolution
  - source/post-mortem
---

## Summary

<!-- Short problem statement. -->

## Context

- **Run date (optional):** YYYY-MM-DD
- **Track:** research / portfolio
- **Document key (optional):** e.g. `pipeline-review/research/YYYY-MM-DD.json`
- **Dedupe key (optional):** must match `<!-- pipeline-review-meta dedupe_key: ... -->` if syncing from `pipeline_review_to_github.py`

## Proposed direction

<!-- What should change: skill, Cowork task, script, prompt, etc. -->

## Acceptance criteria

- [ ] Deterministic validation still passes (`validate_artifact.py`, `validate_db_first.py` as applicable)
- [ ] PR links this issue (`Closes #NNN`)
