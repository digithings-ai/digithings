---
name: beliefs-distillation-daily
description: >
  Short daily fold of newly resolved decision_log lessons into yesterday's beliefs
  body. Cheap-tier, tight token budget; not a full rewrite and not a second digest.
---

# Daily Beliefs Short Fold

You receive ``prior_beliefs_body`` (yesterday's beliefs, possibly empty) and
``resolved_lessons`` (newly unfolded ``decision_log`` rows). Fold **today's
lessons only** into the prior body. Keep the document short: at most four short
paragraphs. Do not restatement-dump every lesson. Do not invent scores, a
Signals section, or a full rewrite of the corpus.

If there is nothing new, say so in one paragraph and carry the prior body
unchanged.

Return JSON validating against the ``BeliefsBlob`` schema: ``schema_version``,
``doc_type`` (must be ``beliefs``), ``date``, and ``body``.
