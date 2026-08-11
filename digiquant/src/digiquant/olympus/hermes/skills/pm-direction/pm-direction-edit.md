# PM Direction Memo — edit mode

Patch the prior `pm-direction-memo` document. Update only sections that changed given new
analyst/deliberation inputs. Preserve unchanged ticker rows.

**Never add weight fields.** Direction (`long`|`flat`) and `conviction_rank` only.

Return `DocumentPatch` when patching; return a full `PMDirectionMemo` body when a rewrite is cleaner.
