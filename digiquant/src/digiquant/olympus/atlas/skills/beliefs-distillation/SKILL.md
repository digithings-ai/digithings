---
name: beliefs-distillation
description: >
  Distill resolved decision lessons and active theses into one durable beliefs
  document for the Portfolio Manager. Cheap-tier call used for the operator
  full rewrite (``refresh_scope=beliefs``) and for backlog catch-up above
  ``OLYMPUS_BELIEFS_BACKLOG``. Daily house runs use ``beliefs-distillation-daily``.
---

# Beliefs Distillation

You receive resolved ``decision_log`` lessons and active thesis rows. Synthesize durable
portfolio beliefs — recurring patterns, factor tilts, and stance calibration lessons —
into a concise body (3–8 short paragraphs). Do not restate every lesson verbatim.

Return JSON validating against the ``BeliefsBlob`` schema: ``schema_version``, ``doc_type``
(must be ``beliefs``), ``date``, and ``body``.
