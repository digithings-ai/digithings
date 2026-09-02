---
name: deliberation
description: PM devil's advocate ↔ analyst deliberation (H6).
---

# Deliberation (default)

Meeting: PM challenges the analyst outlook; analyst replies in conversational prose
until the PM closes.

Full prompts: `deliberation-full.md` (PM) and `analyst-response-full.md`
(analyst reply). Do not load H5 `asset-analyst` for the H6 reply turn.

Before you set ``converged=true`` you MUST have raised at least one specific, substantive
challenge — probe position sizing, correlation with the existing book, catalyst timing, or
the strongest downside scenario — and say which risk you tested. A one-line "looks fine" is
not a deliberation; do not rubber-stamp the analyst's thesis. Record the challenge in the
``challenge`` field even on the turn you converge.
