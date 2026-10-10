# Web-Search Follow-ups Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every remaining #3871 code/docs item (P1 fail-open catch, force-path gate, compat default, dead param, stale docs, orchestrator pin test) in one task PR, leaving only owner-ops items (key issuance, env, limiter, live e2e, GPL sign-off, digest pin).

**Architecture:** No behavior redesign — small surgical fixes at the exact lines verified on develop: fail-closed catch, tenant-gated force arm, compat default flip, dead-code removal, copy updates, one surfacing test.

**Tech Stack:** Python 3.12, Pydantic v2, TypeScript digichat (cloudflare/digichat paths on develop), ruff line-length 100.

**Spec:** Issue #3871 P1/P2 code+docs items; owner decisions 2026-09-12 (arm-point gating for force path; storage-throw→false / missing-key→true / SSR→defaultOn).

## Global Constraints

- Python 3.12, Pydantic v2, strict typing, ruff line-length 100, `ruff check + format --check` zero errors; TS `npm run lint` zero errors.
- Lowercase digi names in prose/docs/commits.
- DataTap stays OFF end-to-end (gate false + no catalog entry + toggle hidden + send blocked + BFF deny) — every task re-verifies this.
- Fail-closed preserved; no new ports/scopes/deps; no BFF route-logic changes.
- Every change traces to #3871 (`task/3871-…` branch, `Fixes #3871` in PR body).
- Human gate: none triggered (no auth/crypto implementation change, no new exposure, no live-trading).

---

### Task 1: Frontend hardening (catch, force arm, compat default, comments)

**Files:**
- Modify: `cloudflare/digichat/src/lib/web-search-pref.ts` (catch → `false`; keep missing→defaultOn, SSR-undefined→defaultOn)
- Modify: `cloudflare/digichat/src/components/assistant-ui/skins/digichat.tsx` (gate force-web arm on tenantAllowsWeb where mentions are already tenant-filtered ~:199; keep BFF deny as backstop, touch nothing in route.ts)
- Modify: `cloudflare/digichat/src/lib/deploy-config/loader.ts:70` + `embed-bridge.ts:29` (injected `default:false` → `default:true`)
- Modify: `cloudflare/digichat/src/lib/embed-tenants.ts:98-102` + `embed-client-config.ts:~124` comments (default-ON wording)
- Test: extend `web-search-pref.test.ts` (3 branches: missing→true, stored-0→false, throw→false), force-arm test (datatap-shape tenant typing `/websearch foo` emits no pending flag), loader duplicate datatap-deny test

**Interfaces:**
- Consumes: tenantAllowsWeb predicate + isWebSearchEnabled AND-gate (unchanged).
- Produces: fail-closed malfunction behavior; tenant-gated force arm; compat tenants default-ON.

- [ ] **Step 1: Write the failing tests**

```ts
it("fails closed on storage throw, defaults on when missing", () => {
  expect(readWebSearchPref("fresh-scope")).toBe(true);
  storageThrowOnce();
  expect(readWebSearchPref("fresh-scope")).toBe(false);
});
```

Match real helper names in the files (read first; keep semantics).

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm run test --workspace digichat -- web-search-pref`
Expected: FAIL (catch returns true)

- [ ] **Step 3: Write minimal implementation**

```ts
} catch {
  return false;
}
```

Gate the force-web arm (`digichat.tsx`) on the same tenantAllows signal used for mention filtering; flip the two injected defaults; rewrite the two stale comments.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm run test --workspace digichat`
Expected: PASS
Run: `npm run lint --workspace digichat`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add cloudflare/digichat/src/lib/web-search-pref.ts cloudflare/digichat/src/components/assistant-ui/skins/digichat.tsx cloudflare/digichat/src/lib/deploy-config/loader.ts cloudflare/digichat/src/lib/deploy-config/embed-bridge.ts cloudflare/digichat/src/lib/embed-tenants.ts cloudflare/digichat/src/lib/embed-client-config.ts
git commit -m "feat(digichat): fail-closed pref catch, tenant-gated force arm, compat default-on"
```

---

### Task 2: Backend hardening (dead param, comment, rename, orchestrator pin)

**Files:**
- Modify: `digigraph/src/digigraph/llm_client.py:285` (remove dead `del source_count` param + update callers)
- Modify: `digiquant/src/digiquant/research/data/ai_portfolios.py:21` (one-line comment: both `web_grounding` and `ai_portfolios` namespaces must be patched)
- Modify: `digiquant/src/digiquant/research/testing/simulator.py:952` + consumers (`CANNED_WEB_GROUNDING` → `CANNED_TOOL_SEARCH`)
- Test: new orchestrator-level test pinning fail-hard surfacing of a failing `web_search` through `execute()`/registry (read the registry execute path first; pin actual behavior — error dict vs raise — do not change surfacing)

**Interfaces:**
- Consumes: Task 9 public `call_digisearch_web_search` wrapper (patch the public name in the new test, not the private one).
- Produces: no dead params; grep-clean remnant names.

- [ ] **Step 1: Write the failing test**

```python
def test_orchestrator_failing_web_search_surfaced_fail_hard(monkeypatch):
    from digisearch.web_search import service as svc  # adapt to real module path
    monkeypatch.setattr(svc, "run_web_search", lambda req: (_ for _ in ()).throw(RuntimeError("down")))
    out = invoke_web_search_tool({"query": "x"})
    assert out["ok"] is False
```

Read the real invoke path first; assert its actual fail-hard shape (ok:False envelope per #3856).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_orchestrator_invoke.py -v -k web_search`
Expected: FAIL (no such pin test)

- [ ] **Step 3: Write minimal implementation**

Remove the dead param (+ callers), add the comment, rename the constant (+ consumers), add the pin test.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_orchestrator_invoke.py tests/dq/research/test_pipeline_simulation.py -v`
Expected: PASS
Run: `ruff check digigraph/src/digigraph/llm_client.py digiquant/src/digiquant/research/data/ai_portfolios.py digiquant/src/digiquant/research/testing/simulator.py && ruff format --check` same files
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/llm_client.py digiquant/src/digiquant/research/data/ai_portfolios.py digiquant/src/digiquant/research/testing/simulator.py tests/ds/test_orchestrator_invoke.py
git commit -m "feat: web-search hardening batch (dead param, rename, fail-hard pin)"
```

---

### Task 3: Docs consistency (ARCH + models + searxng decision record)

**Files:**
- Modify: `digigraph/ARCHITECTURE.md:479` (synthesis-fallback claim → tool-only fail-hard) + `:893` ("default off" → tenant-gated default-on #3859)
- Modify: `config/digiquant_models.yaml:26` ("cheap synthesis grounding" → tool-only)
- Modify: `digisearch/ARCHITECTURE.md:1037` (cost-win sentence → tool-only; append explicit "searxng floats on latest — digest pin is a networked ops follow-up" owner decision)
- Modify: `frontend/digichat/ARCHITECTURE.md` persistence sentence (session prefs reset on reload; catalog/auth toggles persist to localStorage)

No code, no tests. Verify with `rg "synthesis grounding|default off so web never|cheap synthesis" <files>` returning zero (excluding intentionally historical text).

- [ ] **Step 1: Apply the copy edits per file list**
- [ ] **Step 2: Run `rg` to verify zero stale hits**

Run: `rg -n "synthesis grounding|default off so web never" digigraph/ARCHITECTURE.md config/digiquant_models.yaml digisearch/ARCHITECTURE.md`
Expected: zero matches (or only explicitly historical notes)

- [ ] **Step 3: Commit**

```bash
git add digigraph/ARCHITECTURE.md config/digiquant_models.yaml digisearch/ARCHITECTURE.md frontend/digichat/ARCHITECTURE.md
git commit -m "docs: web-search default-on tool-only consistency"
```

---

## Self-Review

**1. Spec coverage:** #3871 P1/P2 code+docs — catch (T1) ✓, force arm (T1) ✓, compat default (T1) ✓, dead param (T2) ✓, comment (T2) ✓, rename (T2) ✓, orch pin (T2) ✓, ARCH/models/searxng record (T3) ✓. Ops items (key, env, limiter, e2e, GPL, digest) correctly excluded — owner-side.
**2. Placeholder scan:** no TBD/TODO/bare directives; every step names files, commands, expected outputs.
**3. Type consistency:** `readWebSearchPref(scope, defaultOn)` + `isWebSearchEnabled` AND-gate used identically in T1; `ok:False` envelope matches #3856 contract in T2.
