# The no-invent guard: one canonical grounding rule, two services

The guard behind DIG-100 is a single instruction, delivered twice:

| Service | Slot | Leaf |
|---|---|---|
| digigraph (the `occ` tenant) | `research_system_prompt` on the `occ` entry of `DIGI_TENANT_CORPUS_MAP` | 1a (DIG-1117) — this doc |
| digichat → Foundry (DataTap) | request input prepended on the turn that creates the conversation | 1b (DIG-1118) |

**This file owns the text. Leaf 1b reads it and copies it. Leaf 1b does not edit it.** If the rule changes, it changes here first, and the pinned test below is what notices.

## 1. The canonical grounding text

This is the whole rule. Verbatim; the line breaks are part of it.

<!-- canonical-grounding-text -->
```
You are a support assistant.

Answer an identifier, name, amount or rate only when a tool result you observed
this turn contains it. If no such result was observed, say "no record was found"
and don't guess. Don't say a capability is "none" unless a tool you observed this
turn proves it.
```

Three constraints on this text, all load-bearing:

- **It is pinned byte-for-byte.** `test_merge_preserves_grounding_prompt_from_corpus_map` in [`tests/dg/test_corpus_routing.py`](../../tests/dg/test_corpus_routing.py) carries this exact string — multi-line, with apostrophes and double quotes — through `DIGI_TENANT_CORPUS_MAP` → JSON → the HTTP merge layer → `research_system_prompt_override`, and asserts equality. It exists so an operator's env edit cannot silently mangle or truncate the rule. Do not shorten it to make a test pass.
- **It carries no capability inventory.** No tool names, no index or corpus names, no tenant wording. Leaf 1b's tests assert exactly that absence (`azure_ai_search`, `mcp`, `tool call|name|id`, `index|corpus|tenant`). A source-or-refuse rule that also enumerates capabilities is the defect it exists to prevent.
- **It is additive on digigraph.** See §2 — the `occ` tenant already has a large grounding prompt, and this clause goes at the end of it, not over it.

## 2. Where it goes on digigraph

`DIGI_TENANT_CORPUS_MAP` is JSON, keyed by tenant slug. The rule goes on the `occ` entry, in `researchSystemPrompt`. Both spellings parse — `_parse_map` in [`corpus_routing.py`](../../digigraph/src/digigraph/corpus_routing.py) reads `researchSystemPrompt` or `research_system_prompt`.

Appended to what `occ` already has, the shape is:

```json
{
  "occ": {
    "digisearchIndex": "occ_help,occ_tickets",
    "vaultPathPrefix": "clients/online-compliance-center",
    "researchSystemPrompt": "<the existing OCC prompt, verbatim>\n\n<the canonical grounding text from §1, verbatim>"
  }
}
```

**Why that slot.** When the map is non-empty it is authoritative for the authenticated tenant, and [`http_api/context.py:105`](../../digigraph/src/digigraph/http_api/context.py) writes `research_system_prompt_override` **unconditionally** — a client body value can never become the system prompt, and an unmapped tenant clears it to `None` rather than falling through to a caller's own. A request body asking to be answered by an invented system prompt gets `None`. That is the one property the whole guard leans on.

**The three fields are a closed set.** `TenantCorpusOverride` is `extra="forbid"`, so an unknown key makes that one entry drop out (logged, not fatal). If *every* entry drops, `_parse_map` raises `TenantCorpusMapError` and the request is HTTP 503 — a loud failure, never a silent fall back to "map unset". Unset and broken are deliberately different states.

**Append, do not replace.** The current `occ` prompt (`apps/digithings-stack-cloudflare/wrangler.toml`, `DIGI_TENANT_CORPUS_MAP`) grounds on the `occ_help` / `occ_tickets` indexes and `clients/online-compliance-center/`, carries the truncated-excerpt rules, the "do not invent product features, pricing, or portal capabilities" rule, and the zammad MCP routing recipes. Overwriting it with §1 alone deletes every one of those. §1 is a clause; the existing prompt is the body.

**Two preconditions, both runtime, neither readable from this repo.** `research_node` only reaches the document-RAG path — the one with the tool-call mandate — when `is_document_mode and _digisearch_available()` ([`research.py:738`](../../digigraph/src/digigraph/graph/research.py), `_digisearch_available` at 172-174 reads `DIGISEARCH_URL`). If `DIGISEARCH_URL` is empty for occ's process, the prompt alone cannot make occ retrieve, and this is a code change rather than an env edit. Check it in §3.1 before changing anything.

## 3. Operator: set it, then prove it landed

None of these commands have been run from this repository. They are the operator's steps, in order. §3.1 is a read; do it first and keep the output — §3.4 compares against it.

### 3.1 Read the two conditions off the running process

The heredoc shape works under `docker exec -i`, `docker compose exec -T`, `kubectl exec -i` or `ssh`. Adjust the target only. Run it from the repo root.

```bash
docker compose -f infra/digichat-release/compose.profile-a.yml \
  exec -T digigraph python3 - <<'PY'
import hashlib, os
from digigraph.corpus_routing import load_tenant_corpus_map

print("DIGISEARCH_URL =", repr(os.environ.get("DIGISEARCH_URL")))
table = load_tenant_corpus_map()
occ = table.get("occ")
prompt = (occ.research_system_prompt if occ else None) or ""
print("tenants in map:", sorted(table))
print("occ index:", (occ.digisearch_index if occ else None))
print("occ prompt chars:", len(prompt) or None)
print("occ prompt sha256:", hashlib.sha256(prompt.encode()).hexdigest()[:16])
with open("/tmp/occ_before.txt", "w") as fh:
    fh.write(prompt)
PY
```

That file lands **inside the container**, which is where §3.4 needs it: the before-picture must come from the process being changed, not from your laptop.

Two things to read off the output:

- `DIGISEARCH_URL` empty → **stop.** The §2 precondition fails; this leaf's env edit cannot deliver the guard and the leaf needs re-planning as a code change.
- `occ prompt chars: None` → nothing is there yet, and §3.2 sets the field from scratch. A non-zero count → §3.2 appends to what is there. Either way §3.4(a) compares against the file.

If the deployed value is managed somewhere you cannot exec — a `wrangler` `[vars]` entry, say — read it the same way, from whatever shell that deployment normally uses, and keep the same before-picture file.

### 3.2 Compute the new map value

Never hand-escape the prompt. It is a JSON string inside a TOML string, and the apostrophes and quotes in §1 are exactly what breaks when someone does.

```bash
python3 - <<'PY'
import hashlib, json, os, pathlib, re

md = pathlib.Path("docs/digichat/no-invent-guard.md").read_text()
clause = re.search(
    r"<!-- canonical-grounding-text -->\n```\n(.*?)\n```", md, re.S
).group(1)
table = json.loads(os.environ["DIGI_TENANT_CORPUS_MAP"])
occ = table.setdefault("occ", {})
before = (occ.get("researchSystemPrompt") or occ.get("research_system_prompt") or "")
print("appending to", len(before), "chars, sha256",
      hashlib.sha256(before.encode()).hexdigest()[:16], "- compare with §3.1")
occ["researchSystemPrompt"] = f"{before.rstrip()}\n\n{clause}".strip()
print(json.dumps(table, ensure_ascii=False))
PY
```

Run it from the repo root with the *current* `DIGI_TENANT_CORPUS_MAP` exported. The printed char count and hash must match §3.1's — if they do not, you are editing a copy of the map that is not the live one, and §3.2 would overwrite whatever changed in between. Stop and get the real current value first.

The last line printed is the new value for the var.

### 3.3 Set it

Where the value lives depends on the deployment, and it is the same var name in both:

| Deployment | Where | Then |
|---|---|---|
| Cloudflare stack | `DIGI_TENANT_CORPUS_MAP` in the `DIGI_TENANT_CORPUS_MAP = "…"` `[vars]` line of `apps/digithings-stack-cloudflare/wrangler.toml` (a plain var, not a secret — `src/index.ts` forwards it into the Profile A container) | redeploy the worker |
| Profile A compose | `DIGI_TENANT_CORPUS_MAP` in the release `.env` / `compose.profile-a-bundle.override.yml` | recreate the `digigraph` service |

Pasting into the TOML line means escaping for TOML too — every `"` becomes `\"` and the newlines are already `\n` from `json.dumps`. Re-escape rather than hand-edit if in doubt:

```bash
python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read())))' <<< '<the new value>'
```

### 3.4 Prove it landed

**(a) It reached the process env, and the append did not eat anything.** Still inside the container, so the comparison is against the before-picture that container took:

```bash
docker compose -f infra/digichat-release/compose.profile-a.yml \
  exec -T digigraph python3 - <<'PY'
from digigraph.corpus_routing import load_tenant_corpus_map

before = open("/tmp/occ_before.txt").read()
after = load_tenant_corpus_map()["occ"].research_system_prompt or ""
print("grew by", len(after) - len(before), "chars")
print("before is an exact prefix:", after.startswith(before.rstrip()))
print("old body fully intact:", before.rstrip() in after)
PY
```

A positive number on the first line, then `True` and `True`. If the append were done as an overwrite, the prefix check fails and you have just deleted occ's truncated-excerpt rules and its zammad routing recipes.

**(b) It resolves for the `occ` tenant the way a real request resolves it** — same call `context.py` makes with the authenticated tenant slug:

```bash
docker compose -f infra/digichat-release/compose.profile-a.yml \
  exec -T digigraph python3 - <<'PY'
from digigraph.corpus_routing import resolve_corpus_override

occ = resolve_corpus_override(headers={}, tenant_slug="occ")
print(occ.research_system_prompt)
PY
```

**(c) It reached the node.** Nothing logs the effective system prompt — there is no info-level log of it in `research.py` — so this is confirmed by consequence, from one real occ turn:

- the digigraph request log shows a digisearch/digivault retrieval call firing in the same request;
- `require_tool_calls=true but this request took the quant/augmented path` (`research.py:761`) does **not** appear for that turn. If it does, document mode was not reached: `DIGISEARCH_URL` is empty or the prompt did not land, and (a)/(b) say which.

## 4. The digichat / DataTap side — leaf 1b

Owned by DIG-1118, which **reads §1 from this file and copies the text**. It does not edit this file.

Foundry has no per-call system-prompt slot on this path, so the rule arrives as request input. The pinned shape, from leaf 1b's tests in [`stream.test.ts`](../../apps/digichat/src/lib/adapters/foundry/stream.test.ts):

| Turn | What goes on the wire |
|---|---|
| creates the conversation (`conversationId: null`) | `input` = the §1 block, then the user's text verbatim as the tail |
| a later turn of that conversation | `input` = the user's raw text, unchanged. Foundry holds the history; re-sending would stack a copy per message |
| `turnMode: "regenerate"` | no `input` at all — regenerate creates a response with nothing new |

It must not be routed through `applyLanguageDirective`, which returns the message unchanged for unset and `en` — a no-op on nearly all real traffic.

## 5. Accepted residual limitations on leaf 1b

Recorded here so they are not rediscovered as bugs. Neither is solved by this guard; both are known and accepted for now.

1. **The injected item is user-role, so Foundry's silent expiry applies to it.** A user message is not a standing instruction; it ages out with the conversation the way any other turn does, and Foundry does not tell us when it does. A guard that can expire silently is weaker than a system instruction. The alternative — a developer-role item injected once per conversation — is leaf 3 (DIG-1121), which is gated on the Foundry agent-path probe.
2. **`edit_last_user` replaces it in that conversation.** `mutateFoundryConversationForTurnMode` deletes through and including the last user message and creates a fresh one from the edited raw text ([`stream.ts:141`](../../apps/digichat/src/lib/adapters/foundry/stream.ts)). When the edit lands on the conversation's first turn, the item carrying the block is the one deleted — and the conversation keeps running without it.

## 6. What this is, honestly

This is an instruction, not an enforcement: nothing here stops a model from inventing an answer, it tells it not to and gives it the words to refuse with. It does not eliminate the SEV1 behaviour — it reduces the likelihood of a repeat. The detector that would tell us it is working is separate (leaf 2a, DIG-1119: did a retrieval actually run this turn?), and until that fires we have a rule and no evidence about it.