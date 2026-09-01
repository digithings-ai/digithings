# PM Direction Memo — edit mode

Patch the prior `pm-direction-memo` document. Update only sections that changed given new
analyst/deliberation inputs. Preserve unchanged ticker rows.

**Never add weight fields.** Direction (`long`|`flat`), `conviction_rank` (order, not size),
and `confidence` in `[0, 1]`. Do not emit `forecast_reference`.

Return `DocumentPatch` when patching; return a full `PMDirectionMemo` body when a rewrite is cleaner.
