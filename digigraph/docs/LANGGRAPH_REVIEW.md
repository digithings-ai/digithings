# DigiGraph vs LangGraph: Usage Review and Recommendations

This document compares the current DigiGraph implementation to LangGraph’s design and capabilities, and suggests concrete improvements so we use the runtime correctly and take advantage of its features.

---

## 1. What We Do Today (Summary)

| Area | Current DigiGraph usage |
|------|-------------------------|
| **Graph shape** | Linear: `START → research → [backtest] → END`. No conditional edges, no subgraphs. |
| **State** | `WorkflowState` (TypedDict, `total=False`). Keys: prompt, session_id, strategy_name, symbols, research_note, research_response, backtest_result, error, stored_datasets, stream_callback. No reducers (no `Annotated[..., operator.add]` or similar). |
| **Invoke** | `graph.invoke(initial, config={"configurable": {"thread_id": session_id or "default"}})`. Single call; we only consume the final state. |
| **Checkpointing** | Optional: `DIGI_CHECKPOINTER=memory` → `MemorySaver`. When set, state (including `stored_datasets`) is persisted per thread. We do not use `get_state`, `get_state_history`, `update_state`, or replay. |
| **Streaming** | Custom: we pass `stream_callback` in state; the research node runs an internal tool loop and calls the callback for tool_call/tool_result/content. We do **not** use `graph.stream()`, `stream_mode`, or LangGraph’s native streaming. |
| **Interrupts / human-in-the-loop** | Not used. No `interrupt_before`, `interrupt_after`, or `Command` to resume. |
| **Multi-turn** | Each HTTP request is one `invoke()`. Conversation history is not in state; the research node sees only the current prompt. For Sitaas, “multi-turn” is effectively a new prompt per request; checkpointing preserves `stored_datasets` for the same thread_id across requests if the client reuses session_id. |

---

## 2. Correctness: Are We Using LangGraph Right?

**What we do correctly:**

- **StateGraph and state:** We use `StateGraph(WorkflowState)` and return dicts from nodes that update state. LangGraph merges those updates; with no reducers, later keys overwrite earlier ones, which matches our linear flow.
- **thread_id:** We pass `config={"configurable": {"thread_id": session_id or "default"}}`, which is required for checkpointing. Checkpointer uses this to key state.
- **Checkpointer:** When enabled, we compile with `checkpointer=MemorySaver()`. That persists a checkpoint after each node, so `stored_datasets` (and the rest of state) survives across invokes for the same thread.
- **No heavy data in state:** We keep only refs and profiles in `stored_datasets`, not full result sets, which is appropriate for checkpoint size and serialization.

**Minor correctness / API notes:**

- **Checkpointer name:** We use `langgraph.checkpoint.memory.MemorySaver`. The same instance is reused via `get_checkpointer()` so thread state persists across HTTP requests (see graph/graph.py).
- **stream_callback:** We pass it via `config["configurable"]["stream_callback"]` when streaming (not in state) so the checkpointer never tries to serialize it (msgpack cannot serialize functions; otherwise you get "Type is not msgpack serializable: function"). The research node reads from config first, then falls back to state for backward compatibility. Streaming is **request-scoped only**.
- **stored_datasets semantics:** There is no reducer for `stored_datasets` (or other state keys). Updates are **last writer wins** per key. When we add parallel nodes or accumulation, we will add explicit reducers (e.g. `Annotated[..., operator.add]` or a custom merge) for the affected keys.

---

## 3. Gaps vs LangGraph’s Full Feature Set

### 3.1 Persistence and state APIs

LangGraph provides:

- **get_state(config)** — Return the latest (or a specific) checkpoint for a thread.
- **get_state_history(config)** — List checkpoints for a thread (e.g. for time travel or debugging).
- **update_state(config, values, as_node=...)** — Edit state (e.g. after human review) and optionally control which node runs next.
- **Replay** — Invoke with `checkpoint_id` to replay from a given checkpoint and re-execute only from that point.

We currently use none of these. Implications:

- We cannot surface “current thread state” (e.g. list of `stored_datasets`) to an API or UI without re-running the graph or duplicating logic.
- We cannot implement “edit state and continue” or time-travel debugging without adding calls to these APIs.

**Recommendation:** Add a thin “thread state” API (e.g. `GET /threads/{thread_id}/state`) that calls `graph.get_state(config)` and returns a safe subset (e.g. `stored_datasets`, last response, error). Optionally expose `get_state_history` for debugging or support tools.

### 3.2 State reducers

Our state has no `Annotated` reducers. For the current linear flow (research → backtest), that’s fine: each node overwrites the keys it sets. If we later add:

- Parallel branches that write to the same key, or
- A need to accumulate messages or dataset refs from multiple nodes,

we should define reducers (e.g. `Annotated[list, operator.add]` for a list of refs, or a custom merge for `stored_datasets`) so LangGraph merges updates correctly instead of overwriting.

**Recommendation:** Document that `stored_datasets` is currently “last writer wins” per key. When we introduce parallel nodes or multi-step accumulation, add explicit reducers for the affected state keys.

### 3.3 Native streaming (graph.stream / stream_mode)

We stream by passing a callback in state and having the research node call it during its internal tool loop. LangGraph supports:

- **graph.stream(input, config, stream_mode="values" | "updates" | "messages" | "custom" | "debug")** — Yields state updates or custom events as the graph runs.
- **invoke(..., stream_mode=...)** — Same stream modes on invoke.

Using native streaming would:

- Unify streaming with the graph execution model (each node’s output is a streamed update).
- Allow `stream_mode="updates"` to get per-node state deltas, or a custom mode to emit tool_call/tool_result/content events from inside the research node.

Today we run the whole graph in one thread and push events via a queue; the server then maps those to SSE. We could instead (or in addition) have the server consume `graph.stream(..., stream_mode="custom")` if the research node emits custom events, or use `stream_mode="updates"` and map node outputs to SSE. That would align streaming with LangGraph’s execution and make it easier to add more nodes that contribute to the stream.

**Recommendation:** Consider refactoring streaming so that the research node (or a wrapper) emits events that LangGraph can stream (e.g. via a custom stream mode or by yielding structured updates). Then the server can iterate `graph.stream(..., stream_mode=...)` and forward to SSE instead of relying only on a state-injected callback.

**Implemented:** `run_digigraph_workflow_via_stream(req)` in workflow.py runs the graph with `graph.stream(initial, config, stream_mode="updates")`, consumes the iterator, then gets final state via `graph.get_state(config)` and returns the same `WorkflowResult`. Use for debugging or as a base for mapping per-node updates to SSE. The default Open WebUI path still uses callback + invoke.

### 3.4 Interrupts and human-in-the-loop

LangGraph supports:

- **interrupt_before=["node_id"]** / **interrupt_after=["node_id"]** — Pause before or after a node; the graph returns with state marked interrupted.
- **Command(resume=...)** — Resume from an interrupt by passing a value (e.g. human-approved edit) into the next step.

We don’t use these. For Sitaas, possible use cases:

- Pause after search (or after a delegate agent) so a human can approve or edit the dataset list before the model continues.
- Pause before backtest so a human confirms parameters.

**Implemented:** Set `DIGI_INTERRUPT_AFTER_RESEARCH=1` to compile with `interrupt_after=["research"]`. Call `POST /threads/{thread_id}/resume` (optional body `{"resume": <value>}`) to continue. Requires a checkpointer. See DIGIGRAPH.md. **Recommendation (further):** Keep additional use cases in the backlog. When we add human-in-the-loop (e.g. “approve before running backtest” or “approve export”), compile the graph with `interrupt_after=["research"]` (or the appropriate node), and have the API resume via `graph.invoke(None, config)` or with `update_state` + a resume payload using `Command`.

### 3.5 Conditional edges and routing

Our graph is linear; we don’t use `add_conditional_edges`. LangGraph allows routing the next node based on state (e.g. “if error, go to END; else go to backtest”). We effectively encode “backtest or not” at compile time via `get_enabled_agents()`, not as a runtime branch.

**Recommendation:** Optional improvement: use a single graph with a conditional edge after research, e.g. `if state.get("error") or "backtest" not in enabled: END else "backtest"`. That would make the graph structure more explicit and would set us up for more branches later (e.g. “visualization” vs “backtest” vs “export”).

### 3.6 Subgraphs

We have one flat graph. LangGraph supports subgraphs: a node can be another compiled graph. That fits the “supervisor + Data Science Family” idea in DIGIGRAPH.md: the research “node” could be a subgraph (e.g. search → decide → delegate agents) with its own state and checkpointing.

**Recommendation:** Longer-term. When we split the research node into multiple steps (e.g. plan → search → delegate → synthesize), consider modeling the Data Science Family as a subgraph so its state and flow are isolated and we can checkpoint at both the top level and inside the subgraph.

### 3.7 Store (cross-thread memory)

LangGraph’s **Store** (e.g. `InMemoryStore`, `PostgresStore`) is for data that spans threads (e.g. user preferences, global caches). We don’t use it; Digistore and run storage are session-scoped and keyed by session_id.

**Recommendation:** Use the Store only if we need cross-session or cross-thread data (e.g. shared user profile, rate-limit state). For per-session datasets, Digistore + checkpointed `stored_datasets` is the right split.

### 3.8 Production checkpointers (implemented)

We support `DIGI_CHECKPOINTER=memory|sqlite|postgres`. A shared checkpointer is used so thread state persists across requests. **memory:** built-in `MemorySaver`. **sqlite:** `langgraph-checkpoint-sqlite` (optional dep); `DIGI_CHECKPOINTER_SQLITE_URI` defaults to `~/.digigraph/checkpoints.sqlite`. **postgres:** `langgraph-checkpoint-postgres` (optional dep); `DIGI_CHECKPOINTER_POSTGRES_URI` required. For production, use sqlite or postgres for durable, resumable state. Install with `pip install digigraph[checkpoint-sqlite]` or `[checkpoint-postgres]`.

---

## 4. Summary Table

| Feature | LangGraph capability | Our use | Suggestion |
|--------|-----------------------|--------|------------|
| thread_id in config | Required for checkpointing | Yes | Keep |
| Checkpointer | Memory / SQLite / Postgres | memory/sqlite/postgres via DIGI_CHECKPOINTER; optional deps | Document in DIGIGRAPH.md |
| get_state / get_state_history | Inspect or replay state | Not used | Add thread-state API; optional history for debug |
| update_state / replay | Edit state, resume from checkpoint | Not used | Use when adding human-in-the-loop |
| State reducers | Annotated[..., add] etc. | None | Add when we have parallel or accumulating keys |
| graph.stream() / stream_mode | Native streaming | Not used; custom callback | Consider refactor to stream_mode or custom events |
| interrupt_before/after + Command | Human-in-the-loop | Not used | Backlog for approval flows |
| Conditional edges | Routing by state | No; compile-time branch | Optional: conditional research → backtest/END |
| Subgraphs | Nested compiled graphs | No | Later: Data Science Family as subgraph |
| Store | Cross-thread memory | Not used | Only if we need cross-session data |

---

## 5. Suggested Order of Work

1. **Document and verify** — Confirm MemorySaver vs InMemorySaver in our LangGraph version; document that stream_callback is not persisted.
2. **Thread state API** — Implement `get_state(config)` in an HTTP endpoint or internal API so UIs can show current thread state (e.g. stored_datasets) without re-running.
3. **Streaming alignment** — Evaluate refactoring to use `graph.stream(..., stream_mode=...)` or custom events so streaming is a first-class LangGraph path.
4. **Production checkpointer** — Add SQLite or Postgres checkpointer option and document it for production.
5. **Conditional edges** — Optionally replace compile-time backtest branch with a conditional edge from research.
6. **Interrupts** — When adding human approval steps, use interrupt_after + Command.
7. **Subgraphs** — When splitting research into multiple nodes, consider a Data Science Family subgraph.

This keeps our current usage correct while aligning us with LangGraph’s persistence, streaming, and control-flow features over time.

## 6. Future: subgraphs

When the research node is split into multiple steps (e.g. plan, search, delegate, synthesize), model the Data Science Family as a **compiled subgraph**: a nested graph with its own state schema and optional checkpointer, wired as a single node in the top-level graph. Defer until there is a concrete design to split research.
