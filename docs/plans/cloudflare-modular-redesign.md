# Cloudflare modular redesign — plan

Status: **proposal for approval**. Supersedes the "full elimination" framing:
the target is *every module its own service, scaling independently*, not one
runtime forced onto every workload.

## 1. The goal, stated as a test

A design is right when all four hold:

1. **Every module is independently deployable** — changing search does not
   rebuild auth.
2. **Every module is independently scalable** — search scales on queries, the
   graph on turns, chat on sessions, with no shared instance between them.
3. **Every module can be off** — a module nobody is using costs nothing and
   holds no state that another module needs in memory.
4. **The shared state is explicit** — KV, D1, R2 only. No shared process, no
   shared filesystem, no shared localhost port.

Today's box fails all four: one container, one image, one lifecycle, eight
programs on localhost ports.

## 2. Today, measured

| | |
|---|---|
| Containers declared | 6 (`chat`, `stack`, `digiquant-runner`, `twelvex-runner`, 2× `langfuse`) |
| Stack container | `standard-1` — 0.5 vCPU, 4 GiB, 8 GB disk, 8 programs inside |
| Chat container | `basic` — 0.25 vCPU, 1 GiB, 4 GB disk, Next + Python MCP |
| Idle wake cost | **≤0.4 s** first byte after 5 and 10 min idle; 2.7–3.1 s to a usable composer |
| Bill | **$77/mo** (`DIG-2904`) |

The measured idle wake matters: containers already scale to zero and wake fast.
So this redesign is **not** a latency fix. It is a structure fix.

## 3. Target module map

Each row is one deployable with one responsibility and one interface.

| Module | Runtime | Interface | State | Scales on |
|---|---|---|---|---|
| `chat-web` | container (`basic`) | HTTPS | none (config from KV) | sessions |
| `digigraph` | container (`standard-1`) | HTTP + SSE | Postgres (external) | turns |
| `digisearch` | container (`standard-1`) **or** Worker | HTTP + MCP | Vectorize/D1 *(or Chroma in-container)* | queries |
| `digivault` | **Worker** | HTTP + MCP | D1, R2 | requests |
| `digikey` | **Worker** (built, parked) | HTTPS/JWT | D1, KV | requests |
| `mcp-edge` | Worker (exists) | MCP over HTTPS | none | requests |
| `digiquant`/`twelvex` jobs | **host runner** (code merged) | cron/launchd | R2 | schedule |
| `litellm` | **remove** — alias map to config | — | — | — |
| `searxng` | **remove** — provider swap | — | — | — |
| `redis` | **remove** — DO/KV | — | — | — |
| `seed_chroma` | **remove** — already a no-op | — | — | — |
| `langfuse` | **decide** — 2× `standard-2` is the largest single line | — | — | — |

End state: **3 containers** (chat, graph, search) + **4 Workers** (vault, key,
MCP edge, cron) + host runners. Every one of them can be off without taking
another down.

## 4. Interaction graph

See `docs/architecture/cloudflare-modular-target.html` (today vs target, with
the request paths drawn). The rule it encodes:

- Browser → **Worker edge** (routing, auth, tenant config from KV)
- Worker edge → **chat-web** (page + `/api/chat`)
- chat-web → **digigraph** (turn, SSE) and → **MCP edge** (tools)
- MCP edge → **digisearch** / **digivault** (per-server scope in the JWT)
- digigraph → **digisearch** (retrieval), **digivault** (notes), **digikey** (tokens)
- anything → **D1 / KV / R2**, never to another module's memory

## 5. Cost model

Rates (Cloudflare, Oct 2026): memory $0.0000025/GiB-s, CPU $0.000020/vCPU-s,
disk $0.00000007/GB-s, egress $0.025/GB, all beyond small monthly allowances;
Workers Paid $5/mo.

**Derived cost per 100 awake hours**, assuming 20% CPU utilisation:

| Instance | Memory | CPU | Disk | ≈ total |
|---|---:|---:|---:|---:|
| `basic` (0.25 vCPU, 1 GiB) | $0.90 | $0.36 | $0.10 | **$1.36** |
| `standard-1` (0.5 vCPU, 4 GiB) | $3.60 | $0.72 | $0.20 | **$4.52** |
| `standard-2` (1 vCPU, 6 GiB) | $5.40 | $1.44 | $0.30 | **$7.14** |

### Scenarios at ~400 awake hours/month per module

| Scenario | Composition | ≈ monthly | vs today |
|---|---|---:|---:|
| **Today** | chat `basic` + stack `standard-1` + 2 runners + 2× langfuse | $77 (measured) | — |
| **Modular, chat stays** | chat `basic` 400h + graph `standard-1` 250h + search `standard-1` 300h + Workers $0 | ≈ $31 | **−$46** if langfuse is unused; **+$7** vs the two containers alone |
| **Modular, chat to Worker** | graph 250h + search 300h + Workers | ≈ $25 | −$8 vs the two containers alone |
| **Lean, not split** | one `standard-2` box for graph+search, small services as Workers | ≈ $29 | ≈ today's container cost, no isolation gain |

**The honest reading:** splitting is **cost-neutral to slightly more
expensive** than the two containers it replaces, because memory is billed per
*provisioned* instance type — moving a service out of the box does not shrink
the box. The saving that is real is whichever containers are awake and unused
(today: 2× `langfuse` at `standard-2` is the biggest single line, then the two
runners). **Delete before you split.**

The gain from splitting is structural: independent failure, independent
scaling, no shared localhost, and a module you can switch off.

## 6. Migration phases

| Phase | Work | Exit criterion | Cost effect |
|---|---|---|---|
| 0 | Measure per-container awake hours from Cloudflare analytics | a per-container number replaces the estimate below | informs everything |
| 1 | Delete `redis`, `seed_chroma`; decide `searxng`, `litellm` | box runs fewer processes, same behaviour | −$0 (same instance) |
| 2 | `digivault` → Worker on D1 | vault tools answer without a container hop | −CPU only |
| 3 | `digikey` cut (Worker built) | tokens verify after the cut, compatibility proven | −CPU only |
| 4 | MCP shims → Workers | edge serves every tool with no container | −CPU only |
| 5 | Split graph and search into their own containers | each scales alone; one can be off | ±$0–7 |
| 6 | Chat → Worker *(separate decision, 4 blockers)* | full turn on OCC + house | −$5 |
| 7 | Delete `langfuse` if unused | name gone, no traffic | **−$10–25** |

Phase 7 is worth more than phases 2–6 combined on cost. It should be decided
first, not last.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Splitting *raises* the bill (more instances awake at once) | Phase 0 measurement before Phase 5; keep the box as one instance if awake profiles overlap |
| digikey cut invalidates live tokens | compatibility test with a pre-cut token |
| digisearch port lowers recall | the recall spike gates it; the container stays otherwise |
| Chat port is a rewrite (socket, Python MCP, Postgres, fs) | treated as a separate funded decision, not a migration step |

## 8. What I need from you

1. **Approve the end state**: 3 containers + 4 Workers + host runners.
2. **Decide `langfuse` first** — it is the only change that meaningfully moves
   the bill.
3. **Accept that splitting is cost-neutral**, and is bought for structure, not
   savings.

Until (1) is approved, nothing moves.
