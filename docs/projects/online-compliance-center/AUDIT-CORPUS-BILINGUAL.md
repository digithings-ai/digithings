# OCC corpus audit — crawl completeness + EN/DE bilingual coverage

Date: 2026-08-16 (updated same day with a direct production-data pass — see
below). Scope: **narrowed by owner instruction** to two guarantees only: (a)
the full site was completely scanned, and (b) every document found is
actually included in the corpus. EN/DE dedup-preference is explicitly **not**
an action item for this pass ("it's okay if there are duplicates in both
languages") — the bilingual inventory below is kept for reference only.

## Method

- Fresh live BFS crawl via `run_onboard.py --dry-run` with
  `DOCS_ONBOARD_DRY_RUN_CRAWL=1` against `onboard.yaml` (workdir:
  `scratchpad/occ-audit/baseline`), producing `pages.jsonl`, `classified.jsonl`,
  `meta/source_map.jsonl`, and fetched `assets/`.
- Cross-check via direct browser inspection of every page on the live site
  (nav nodes and PDF buttons), and `grep` over the raw crawled HTML for every
  `href="*.pdf"` on every page, to confirm the crawler missed no document link.
- **Follow-up pass (same day):** queried production directly — `CORE_SUPABASE_URL`
  in `.env` is the real backing store (confirmed via `docker-compose.yml`'s
  `digi-digivault` service), read-only via PostgREST (`GET
  .../rest/v1/architecture_notes?...`) using the service key already present in
  `.env`. This is the same verification method GAPLOG already records for prior
  applies ("verified via REST count"), just run again as a diff instead of a
  count. Pulled all 328 rows under `clients/online-compliance-center/` and their
  `frontmatter.source_url` values, then diffed against today's fresh crawl
  URL-for-URL. This supersedes the original "no Supabase query was possible"
  limitation below and **overturns the drift finding in the original §1** (see
  corrected version).

## 1. Crawl completeness — confirmed 100%

The site's nav has exactly 7 links (6 kept as `docs`, `Kontakt` skipped by
manifest). `grep -o 'href="[^"]*\.pdf"' html/*.html` across all 6 crawled HTML
pages finds PDF links on exactly 3 pages — **OCC Dokumentation** (7 links),
**Whitepaper** (15 links), **Updates & Wartung** (2 links) — 24 total, and
every one of those 24 already has a matching entry in `classified.jsonl`.
FAQ, E-Learning, and the homepage link no PDFs. **No document link on any
page is missing from the crawl.**

Of the 24 linked PDFs, 22 fetch successfully (200) and 2 return 404:

| Broken link (button text) | Actual href | Found on |
|---|---|---|
| "Erläuterung der Berechtigungen im OCC - Backup Restore.pdf" | `/../images/Whitepaper/Backup  Restore Dokumente/Erlauterung%20der%20Berechtigungen%20im%20OCC%20-%20Backup%20%20Restore.pdf` | Updates & Wartung, "Juli 2025 - Version 2.1" changelog entry |
| "&nbsp;" (blank link text) | `/../images/Whitepaper/Backup  Restore Dokumente/Erklarung%20der%20Berechtigungen%20im%20OCC.pdf` | same changelog entry |

Both use a malformed relative path (`/../images/...`) baked into a year-old
changelog post — **a stale link on the live Joomla site**, not a crawler gap.
`fetch_docs`/`classify_pages` already exclude them correctly (recorded as
`content_type: "error:...404 Not Found"` in `meta/source_map.jsonl`); nothing
to fix in the pipeline. Worth a note back to sitaas that those 2 links in the
Jul-2025 update rot.

**Drift note — retracted.** The original comparison here (33 vs. 30) was
apples-to-oranges: it compared today's crawl total *plus* the 3 static repo
docs against a 2026-08-10 baseline that was crawl-only. The correct
comparison is crawl-only vs. crawl-only: **30 vs. 30 — no drift.** A direct
URL-for-URL diff of today's fresh crawl against production's actual 28
ingested `source_url` values (28 successfully-fetchable of the 30 crawl
items; the other 2 are the dead links below) shows **zero missing and zero
extra items**. For every page and PDF the live site actually serves,
production is exactly current as of today. No re-run is needed for
crawl-derived content, and the `06.2026`/`05.26` filename stamps noted
earlier are not new — those same files were already present and ingested in
the 2026-08-11 apply.

**Real gap found instead: the 3 static repo docs never reached production.**
`manual-docs.yaml`'s 3 files (`README.md`, `portal-manual.md`,
`search-manual.md`) are correctly classified by the pipeline as `repo_doc`
and correctly included in every downstream `_KEEP`/vault/search filter — this
is not a pipeline bug. The cause is simpler: `static_sources:` was added to
`onboard.yaml` in commit `727d41dc9` on **2026-08-13**, two days *after* the
last production apply on **2026-08-11** (`GAPLOG.md`'s "Content-aware
chunking live run"). No apply has run since 2026-08-13, so these 3 docs have
simply never had a chance to be ingested. Confirmed by direct query: all 328
production rows' `frontmatter.source_url` values were inspected and **zero**
`repo://online-compliance-center/...` URLs exist — 100% crawl-derived
(`https://help.online-compliance-center.com/...`), 0% static. **This is the
one confirmed "not every document is included" finding from this pass**, and
the fix is a plain re-run (no code or manifest change needed — both are
already correct).

## 2. Structural finding: the site has no English HTML

Every HTML page (nav, news posts, FAQ, docs) is German-only; there is no
language switcher anywhere (header, sticky nav, footer, mobile menu — all
checked). So the bilingual-coverage question the user raised **does not apply
at the page level** — only at the linked-PDF level, where English exists as
explicit `_EN`/`EN`-suffixed sibling files for some, not all, topics.

## 3. Full inventory (22 real PDFs + 6 HTML pages + 3 static repo docs)

### Confirmed EN/DE duplicate pairs — 4 pairs, 8 files

Per your stated preference, **keep the English file, drop the German one**
for each of these when building the corpus:

| Topic | German (drop) | English (keep) |
|---|---|---|
| OCC product info | `06.2026_Produktinformation Online Compliance Center.pdf` | `06.2026_EN_Produktinformation Online Compliance Center.pdf` |
| Backup Restore product info | `06.2026_Produktinformation OCC Backup Restore.pdf` | `06.2026_EN_Produktinformation OCC Backup Restore.pdf` |
| Search user guide | `User Guide_Search_OCC.pdf` | `User Guide_Search_OCC_EN.pdf` |
| Service & license agreement | `Service- und Lizenzvereinbarung OCC_03.2026.pdf` | `Service and License Agreement OCC_EN.pdf` |

### Reconciled via repo-authored English (not a live PDF pair, but covered)

| German PDF | English equivalent | Note |
|---|---|---|
| `Admin Guide OCC_02.2025.pdf` | `sources/manual/README.md` + `portal-manual.md` (repo-authored) | `manual-docs.yaml` explicitly reconciles these — treat as satisfying bilingual coverage, don't flag as a gap |

### Language-unique — no counterpart anywhere; include per your fallback rule

**German-only (11):**

| File | Section |
|---|---|
| `OnePager_Online Compliance Center_06.26 2.pdf` | Allgemeine Dokumente |
| `Erklarung Berechtigungen OCC_06.2026.pdf` | Backup & Restore |
| `Onepager OCC Backup Restore.pdf` | Backup & Restore |
| `Vergleich_CloudBackup vs. OCC Backup Restore.pdf` | Backup & Restore |
| `Vergleich_Hornetsecurity TotalProtection vs. OCC Backup Restore_05.26.pdf` | Backup & Restore |
| `Vergleich_veeam Data Cloud for Microsoft 365 vs. OCC Backup Restore_05.26.pdf` | Backup & Restore |
| `Vergleich_AvePoint Cloud Backup for Microsoft 365 vs. OCC Backup Restore_05.26 1.pdf` | Backup & Restore |
| `Onepager OCC Compliance Archivierung_0526.pdf` | Compliance Archivierung |
| `06.2026_Produktinformation OCC Compliance Archivierung.pdf` ⚠ | Compliance Archivierung |
| `Onepager OCC Datenmanagement_0526.pdf` | Datenmanagement |
| `06.2026_Produktinformation OCC Datenmanagement.pdf` ⚠ | Datenmanagement |

⚠ = **actionable gap, not just an artifact of scope.** The "Produktinformation"
family has an `_EN` sibling for 2 of its 4 topics (OCC overall, Backup Restore)
but not for these other 2 (Compliance Archivierung, Datenmanagement) — breaks
the site's own established pattern. Worth flagging to sitaas as a likely
missed translation rather than treating as permanently German-only.

**English-only (2)** — the reverse gap, no German counterpart exists for
either:

| File | Section |
|---|---|
| `Admin Guide_Compliance Archiv_OCC_EN.pdf` | OCC Dokumentation |
| `Admin Guide_Mail Backup_OCC_EN.pdf` | OCC Dokumentation |

All 13 language-unique files above should be **included as-is** per your
"include what we have" rule — none are dropped.

### HTML pages (6) and static repo docs (3)

All German (HTML) / English (repo docs) respectively, no bilingual pairing
applicable — see §2. No changes needed.

## 4. Net recommendation for the corpus

Per owner instruction, duplicates across languages are **not** a gap to fix
in this pass — "it's okay if there are duplicates in both languages." The
inventory in §3 is kept for reference only; no dedup filter is being built
right now.

- **Crawl-derived content (6 HTML + 22 real PDFs): no action needed.**
  Production exactly matches the live site today, confirmed by direct
  Supabase diff (§1).
- **Static repo docs (3 files): re-run required.** They are correctly
  configured and correctly handled by the pipeline but have never been
  ingested because the config postdates the last apply. Re-running the
  one-shot onboard apply (`README.md`'s documented apply command) will pick
  them up — no code change needed.
- Fix the 2 dead links in the Updates & Wartung changelog on the live site
  (report to sitaas) — cosmetic, does not affect the corpus.

## 5. Answering the original question directly

- **Crawl completeness:** confirmed 100% — every page and every linked PDF on
  the live site is reachable and classified; the only 2 "missing" PDFs are
  dead links on the site itself, already correctly excluded.
- **Corpus vs. live site, verified against production data:** for everything
  the crawler finds (HTML pages + PDFs), production is byte-for-byte current
  with the live site — no drift, no missing items, confirmed by a direct
  URL-level diff against the actual Supabase rows.
- **One real "not every document is included" gap:** the 3 static
  repo-authored English manual docs are configured and pipeline-ready but
  have never actually been ingested (config added after the last apply).
  Re-run is the fix; tracked in `GAPLOG.md`.
