/**
 * Public-site counts — single-sourced (D1, #4429).
 *
 * The landing metrics band and the /quality figures each used to carry their
 * own literals, and they had drifted: /quality's "frontend test files" command
 * even pointed at the retired `frontend/` tree, and its python/workflow figures
 * were stale by hundreds. Every number the two pages render now comes from
 * here, so a refresh is one edit and a figure cannot be restated differently on
 * two pages.
 *
 * Derivable counts are computed — the module split comes from the shared
 * `modules` registry (`@digithings/ui`). The rest are repository snapshots:
 * each carries the exact command that produced it and the date it was run, so
 * a reader can reproduce it and a stale value is visibly dated rather than
 * silently wrong.
 */
import { modules } from "@digithings/ui";

/** The date every snapshot below was counted, on a clean `develop` checkout. */
export const COUNTED_AT = "20 September 2026";

// ── Derivable from the kit registry ────────────────────────────────────────
/** Modules that actually ship (`tier !== "roadmap"`). */
export const SHIPPING_MODULES = modules.filter((m) => m.tier !== "roadmap").length;
/** Modules still on the roadmap; the total comes from the same registry. */
export const ROADMAP_MODULES = modules.length - SHIPPING_MODULES;

// ── Repository snapshots (command recorded beside each) ────────────────────
//
// docker-compose.yml, top-level keys under `services:`                       → 23
export const COMPOSE_SERVICES = 23;
// …of those, services with no `profiles:` key (up under `make up`)          → 10
export const COMPOSE_DEFAULT = 10;
// digisearch backend precedence, fail-closed at startup:
// Cloudflare Vectorize → Azure AI Search → Chroma
// (digisearch/src/digisearch/backend_require.py, require_real_search_backend).
export const SEARCH_BACKENDS = 3;
// BYOK keys persisted: the provider key rides per-request in `x-byok-key` and
// is never stored or logged (apps/digichat/src/app/api/chat/route.ts).
export const BYOK_KEYS_STORED = 0;
// find tests -name 'test_*.py' | wc -l                                      → 809
export const PYTHON_TEST_FILES = 809;
// find apps packages -path '*/node_modules' -prune -o \
//   \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' \
//      -o -name '*.spec.tsx' -o -name '*.test.js' -o -name '*.test.mjs' \) \
//   -print | wc -l                                                          → 455
export const FRONTEND_TEST_FILES = 455;
// ls .github/workflows/ | grep -c '\.yml$'                                  → 74
export const CI_WORKFLOWS = 74;
// ls .github/workflows/ | grep -c '^test-'                                  → 17
export const TEST_LANES = 17;
