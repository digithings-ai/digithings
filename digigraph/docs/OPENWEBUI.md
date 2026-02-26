# Open WebUI: Displaying Internal Steps
## From Thinking to Tool Calls — Complete Reference

---

## Visual Layout

Every message renders top-to-bottom in this order:

```
┌──────────────────────────────────────────────────┐
│  ⟳ Status chip (live spinner while running)      │  ← event_emitter status
│  ✅ Status chip (done, collapsed)                 │  ← event_emitter status done
│  ▶ Thinking...  (collapsible reasoning block)     │  ← <think> tags
│  ▶ 🔧 Tool Call (collapsible tool detail)         │  ← <details> or native FC
│  ──────────────────────────────────────────────  │
│  Main message answer                              │  ← response content
└──────────────────────────────────────────────────┘
```

---

## Method 1 — Reasoning Tags (Thinking Dropdown)

### How it works
Wrap content in a supported tag pair. Open WebUI strips the tags from the visible message and renders the content as a collapsible **"Thinking..."** block with a styled header.

### Supported tags

| Tag | Typical model |
|-----|--------------|
| `<think>` / `</think>` | DeepSeek R1, QwQ, most local models |
| `<thinking>` / `</thinking>` | Anthropic Claude-style |
| `<reason>` / `</reason>` | Generic formal framing |
| `<reasoning>` / `</reasoning>` | Explicit reasoning convention |
| `<thought>` / `</thought>` | Atomic step-by-step models |
| `<\|begin_of_thought\|>` / `<\|end_of_thought\|>` | Qwen / InternLM token-gated models |

### Basic example

```
<think>
The user asked for the capital of France.
There is only one correct answer — Paris.
No ambiguity, no need to hedge.
</think>

The capital of France is Paris.
```

**Renders as:**
```
▶ Thinking...
──────────────
The capital of France is Paris.
```

### Multi-step reasoning example

```
<think>
Step 1: Parse the user's question — they want a Python function that reverses a string.
Step 2: Consider edge cases — empty string, single char, Unicode.
Step 3: Decide on approach — slicing with [::-1] is idiomatic Python.
Step 4: Should I add type hints? Yes, good practice.
</think>

Here is a Python function to reverse a string:

```python
def reverse_string(s: str) -> str:
    return s[::-1]
```
```

### Configuration

- **Per-chat:** Chat Controls → Advanced Parameters → Reasoning Tags
- **Per-model:** Workspace → Models → Edit → Advanced Parameters → Reasoning Tags

| Value | Effect |
|-------|--------|
| Default | Detects all built-in tag pairs |
| Enabled | Force-enables using `<think>` |
| Disabled | Turns off detection entirely |
| Custom | Specify your own start/end tag |

---

## Method 2 — Custom Title Thinking Block (Collapsible Thought Filter)

### How it works
Install the **Collapsible Thought Filter** community function. It intercepts output, finds your reasoning tag, and wraps it in a `<details>` block with whatever title you set in the Valves — while keeping the native styled appearance.

### Install
Workspace → Functions → + New Function → search **"Collapsible Thought Filter"** by `projectmoon`

### Valve settings

| Valve | Example value | Effect |
|-------|--------------|--------|
| `thought_title` | `🧠 Reasoning Steps` | The label shown on the collapsed block |
| `thought_tag` | `thinking` | The XML tag to look for in the output |
| `output_tag` | `output` | The tag wrapping the final answer |

### Example model output format

```
<thinking>
The user wants a SQL query joining orders and customers.
I should use an INNER JOIN on customer_id.
I'll alias the tables for readability.
</thinking>

<output>
Here is the SQL query:

```sql
SELECT o.order_id, c.name, o.total
FROM orders o
INNER JOIN customers c ON o.customer_id = c.id;
```
</output>
```

**Renders as:**
```
▶ 🧠 Reasoning Steps     ← your custom title
──────────────────────────
Here is the SQL query: ...
```

---

## Method 3 — Status Event Emitter (Spinner / Progress Chip)

### How it works
Call `__event_emitter__` with `type: "status"` from a Tool or Pipe. A chip appears above the message while processing, with a spinner that collapses when done.

### Single step

```python
async def my_tool(self, query: str, __event_emitter__=None) -> str:

    await __event_emitter__({
        "type": "status",
        "data": {
            "description": "🔍 Searching knowledge base...",
            "done": False
        }
    })

    result = search(query)

    await __event_emitter__({
        "type": "status",
        "data": {
            "description": "✅ Search complete",
            "done": True
        }
    })

    return result
```

**Renders as:**
```
⟳ Searching knowledge base...    ← spinner, live
✅ Search complete                ← collapses to chip
──────────────────────────────────
Answer based on results...
```

### Multi-step pipeline

```python
async def pipe(self, body: dict, __event_emitter__=None) -> str:

    steps = [
        ("🔐 Authenticating with API...", authenticate),
        ("📡 Fetching records...",         fetch_records),
        ("🧹 Filtering results...",        filter_results),
        ("🧮 Scoring and ranking...",      rank_results),
    ]

    data = body["messages"][-1]["content"]

    for label, fn in steps:
        await __event_emitter__({"type": "status", "data": {
            "description": label, "done": False
        }})
        data = fn(data)
        await __event_emitter__({"type": "status", "data": {
            "description": label.replace("...", " ✓"), "done": True
        }})

    return summarise(data)
```

**Renders as:**
```
✅ Authenticating with API ✓
✅ Fetching records ✓
✅ Filtering results ✓
✅ Scoring and ranking ✓
─────────────────────────
Here are your top results...
```

### Status field reference

| Field | Type | Values |
|-------|------|--------|
| `description` | string | Text shown in the chip |
| `done` | bool | `false` = spinner active · `true` = step complete |
| `hidden` | bool | `true` = hide chip entirely after done (silent step) |

---

## Method 4 — `<details>` Block (Custom Expandable Section)

### How it works
Inject raw HTML into the message content via the `message` event emitter. The `<summary>` tag is the visible label; everything inside is the expanded content. Markdown renders inside.

### Basic tool call display

```python
await __event_emitter__({
    "type": "message",
    "data": {
        "content": """
<details>
<summary>🔧 Tool Call: search_web</summary>

**Input**
```json
{"query": "Azure OpenAI pricing 2025"}
```

**Output**
```json
[
  {"title": "Azure Pricing Page", "url": "https://azure.microsoft.com/pricing/", "snippet": "..."},
  {"title": "OpenAI on Azure FAQ", "url": "https://learn.microsoft.com/...", "snippet": "..."}
]
```
</details>
"""
    }
})
```

**Renders as:**
```
▶ 🔧 Tool Call: search_web
──────────────────────────
(expanded view shows JSON input + output)
```

### Multi-tool sequence

```python
tools_called = [
    {
        "name": "fetch_user_profile",
        "input": {"user_id": 42},
        "output": {"name": "Alice", "tier": "premium", "score": 98}
    },
    {
        "name": "fetch_recommendations",
        "input": {"tier": "premium", "limit": 5},
        "output": {"items": ["Product A", "Product B", "Product C"]}
    }
]

for tool in tools_called:
    import json
    block = f"""
<details>
<summary>🔧 {tool['name']}</summary>

**Input**
```json
{json.dumps(tool['input'], indent=2)}
```

**Output**
```json
{json.dumps(tool['output'], indent=2)}
```
</details>
"""
    await __event_emitter__({"type": "message", "data": {"content": block}})
```

**Renders as:**
```
▶ 🔧 fetch_user_profile
▶ 🔧 fetch_recommendations
──────────────────────────
Based on Alice's premium profile, here are your top picks...
```

---

## Method 5 — `<details type="reasoning">` (Styled Like Thinking Block)

### How it works
Same as `<details>` but uses the `type="reasoning"` attribute, which Open WebUI renders using the same styled component as the native `<think>` dropdown — visually consistent with the thinking block.

### When to use
Use this when you want tool context or RAG results to look identical to model reasoning — creating one unified visual language for all "behind the scenes" content.

### Example

```python
context_block = """
<details type="reasoning">
<summary>📚 Knowledge Base — Azure AI Search</summary>

**Query:** What is the refund policy for enterprise plans?

**Result 1** (score: 0.94) — Source: `policies/enterprise-terms.pdf`
Enterprise plans are eligible for pro-rated refunds within 30 days of billing.
Contact enterprise-support@company.com for requests.

**Result 2** (score: 0.87) — Source: `faq/billing.md`
Annual enterprise contracts may be cancelled with 60 days written notice.
</details>
"""

final_answer = "Based on our enterprise terms, you are eligible for a pro-rated refund..."

return context_block + "\n\n" + final_answer
```

**Renders as:**
```
▶ 📚 Knowledge Base — Azure AI Search   ← styled like Thinking block
──────────────────────────────────────────
Based on our enterprise terms, you are eligible for...
```

---

## Method 6 — Native Function Calling (Zero-Code Auto Display)

### How it works
Enable Native Function Calling mode and Open WebUI automatically renders tool call arguments and results in a structured block — no event emitters or injected HTML needed.

### Enable
Chat Controls → Advanced Parameters → Function Calling → **Native**

### What gets displayed automatically

```
▶ Tool: search_knowledge_base
   query: "refund policy enterprise"
▶ Result
   [{"source": "...", "content": "..."}]
──────────────────────────────────────
The refund policy states...
```

### Compatibility

| Backend | Native FC support |
|---------|-------------------|
| OpenAI-compatible APIs | ✅ |
| Ollama | ✅ |
| Anthropic extended thinking | ❌ Use pipe function instead |
| OpenAI o-series | ⚠️ Limited (reasoning is internal) |

---

## Full Pipeline Example — All Methods Combined

This example shows every method working together in a single Pipe function for a knowledge-base-backed assistant.

```python
"""
title: Azure KB Assistant with Full Step Visibility
"""
import json
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.core.credentials import AzureKeyCredential
from pydantic import BaseModel, Field


class Pipe:

    class Valves(BaseModel):
        SEARCH_SERVICE: str = Field(default="")
        SEARCH_INDEX:   str = Field(default="")
        SEARCH_API_KEY: str = Field(default="")
        TOP_K: int = Field(default=3)

    def __init__(self):
        self.valves = self.Valves()

    async def pipe(self, body: dict, __event_emitter__=None) -> str:

        user_query = body["messages"][-1]["content"]

        # ── Step 1: Status chip ──────────────────────────────────────────
        await __event_emitter__({"type": "status", "data": {
            "description": "📡 Querying Azure AI Search...", "done": False
        }})

        # ── Step 2: Query the index ──────────────────────────────────────
        client = SearchClient(
            endpoint=f"https://{self.valves.SEARCH_SERVICE}.search.windows.net/",
            index_name=self.valves.SEARCH_INDEX,
            credential=AzureKeyCredential(self.valves.SEARCH_API_KEY),
        )
        vector_query = VectorizableTextQuery(
            text=user_query, kind="text",
            k_nearest_neighbors=self.valves.TOP_K, fields="embedding"
        )
        results = list(client.search(
            search_text=user_query, top=self.valves.TOP_K,
            query_type="semantic", semantic_configuration_name="default",
            vector_queries=[vector_query],
        ))

        await __event_emitter__({"type": "status", "data": {
            "description": f"✅ Retrieved {len(results)} passages", "done": True
        }})

        # ── Step 3: Show retrieval detail in reasoning-style block ───────
        kb_detail = "\n\n".join(
            f"**Result {i+1}** (score: {r.get('@search.reranker_score', 'N/A'):.2f})"
            f" — Source: `{r.get('sourcefile', 'unknown')}`\n{r.get('content', '')}"
            for i, r in enumerate(results)
        )
        await __event_emitter__({"type": "message", "data": {"content": f"""
<details type="reasoning">
<summary>📚 Knowledge Base Results</summary>

**Query:** {user_query}

{kb_detail}
</details>
"""
        }})

        # ── Step 4: Build context + call the model ───────────────────────
        context = "\n\n---\n\n".join(r.get("content", "") for r in results)

        await __event_emitter__({"type": "status", "data": {
            "description": "🤔 Generating answer...", "done": False
        }})

        # Model output — wrap any chain-of-thought in <think> tags
        # so it appears as a separate Thinking block above the answer
        model_response = call_model(
            system=f"Use the following context to answer:\n\n{context}",
            user=user_query
        )
        # model_response expected format:
        # <think>reasoning here</think>
        # Final answer here...

        await __event_emitter__({"type": "status", "data": {
            "description": "✅ Done", "done": True
        }})

        return model_response
```

### What the user sees

```
✅ Retrieved 3 passages
✅ Done
▶ 📚 Knowledge Base Results     ← <details type="reasoning"> block
▶ Thinking...                    ← <think> block from model output
────────────────────────────────
Based on the enterprise terms...  ← main answer
```

---

## Quick Reference

| Method | Trigger | Label control | Style | Needs code? |
|--------|---------|---------------|-------|-------------|
| `<think>` tag | Model output | ❌ "Thinking..." fixed | ✅ Native styled | No |
| Collapsible Thought Filter | Model output | ✅ Valve setting | ✅ Native styled | No (install filter) |
| `status` event emitter | Tool / Pipe code | ✅ Full control | Chip / spinner | Yes |
| `<details><summary>` | Tool / Pipe code | ✅ Full control | Plain dropdown | Yes |
| `<details type="reasoning">` | Tool / Pipe code | ✅ Full control | ✅ Native styled | Yes |
| Native Function Calling | Auto (FC mode on) | ❌ Auto-generated | Auto block | No |

---

## Emoji Conventions (Recommended)

Using consistent emoji prefixes makes it easy to scan the step trail at a glance:

| Emoji | Suggested use |
|-------|--------------|
| 🔍 | Search / retrieval step |
| 📚 | Knowledge base query |
| 🔧 | Tool call |
| 📡 | External API call |
| 🧠 | Reasoning / thinking |
| 🔐 | Auth / credentials |
| 🧹 | Cleaning / filtering data |
| 🧮 | Calculation / scoring |
| ✅ | Step complete |
| ❌ | Step failed |
| ⚠️ | Warning / partial result |

---

## Tool‑Specific Output & Open WebUI Formatting

This section describes how DigiGraph tools and delegate agents format their
results so that the Open WebUI formatter can render tables, images, mermaid
diagrams, and summaries instead of dumping raw JSON.

### Overview of behaviour

1. **Tool call** – whenever the graph invokes a tool we emit:
   ```html
   <details><summary>🔧 Tool Call: {name}</summary>
   <pre>{args (JSON)}</pre>
   </details>
   ```
   OWU turns this into a dropdown labelled “🔧 Tool Call: digisearch”, etc.

2. **Tool result** – when the tool returns we stream another `<details>`
   block with the payload.  The formatter now receives
   `{"name": "digisearch", ...}` so it can branch on the tool name.

3. **Delegate tools** – results from `visualization_agent`,
   `analysis_agent` and `data_prep_agent` are JSON strings that in turn contain
   keys such as `image_path`, `mermaid_source`, `table`, etc.  The formatter
   parses that JSON and emits appropriate markdown or images.

4. **Summary line** – every result block begins with a one‑sentence summary
   (e.g. “Generated distribution plot; 42 points.”) so the OWU UI remains
   scannable even when many tool calls are made.

5. **Errors** – if a payload contains an `error` field it is shown clearly as
   bold text rather than buried in JSON.


### Tools & expected output keys

The following tables enumerate every tool that DigiGraph or its sub‑agents may
return.  The *formatter* uses these keys to decide how to render the result for
Open WebUI.

#### Orchestrator (research node) tools

| Tool | Description | Output shape (to LLM / stream) |
|------|-------------|--------------------------------|
| **digisearch** | Search the document index (DigiSearch). | `content`, `results`, `summary`, `dataset_ref` (storage path when `run_data_dir` set). **Storage path is shown in the result** so the same retrieval can be reused without re‑running search. OWU: table + “Stored at: …” line. |
| **visualization_agent** | Delegate to visualization specialist. | `content`: JSON string from sub‑agent (see visualization tools below). |
| **analysis_agent** | Delegate to analysis specialist. | `content`: JSON string from sub‑agent (see analysis tools below). |
| **data_prep_agent** | Delegate to data prep (export, filter, sample). | `content`: JSON string from sub‑agent (see data prep tools below). |

#### Visualization family tools

| Tool | Output keys | OWU formatting |
|------|-------------|----------------|
| **plot_distribution** | `image_path`, `summary`, `error?` | Show image (base64 or URL), short summary. |
| **plot_time_series** | `image_path`, `summary`, `error?` | Same. |
| **plot_categorical** | `image_path`, `summary`, `error?` | Same. |
| **plot_scatter** | `image_path`, `summary`, `error?` | Same. |
| **plot_sankey** | `image_path`, `summary`, `error?` | Same (flow diagram image). |
| **build_relationship_graph** | `graph`, `image_path?`, `mermaid_source?`, `error?` | Image and/or Mermaid block. |
| **entity_co_occurrence** | `pairs`, `image_path?`, `mermaid_source?`, `error?` | Table of pairs + optional image/Mermaid. |
| **generate_mermaid_diagram** | `mermaid_source`, `error?` | Mermaid code block only. |

#### Analysis family tools

| Tool | Output keys | OWU formatting |
|------|-------------|----------------|
| **correlation_matrix** | `matrix`, `image_path?`, `error?` | Render as markdown table (rows=columns) and/or heatmap image. |
| **simple_regression** | `slope`, `intercept`, `r_squared`, `equation`, `image_path?`, `error?` | Equation + residual plot image. |
| **summary_stats** | `stats` (per-column mean/median/std/min/max/null_count), `error?` | Markdown table of stats. |
| **group_by_summary** | `table`, `columns`, `error?` | Markdown table. |
| **pivot_table** | `table`, `columns`, `error?` | Markdown table. |
| **cluster_metadata** | `labels`, `summary`, `n_clusters`, `error?` | Short summary + optional table. |

#### Data prep family tools

| Tool | Output keys | OWU formatting |
|------|-------------|----------------|
| **export_dataset** | `path`, `format`, `rows`, `download_url?`, `error?` | Message: “Exported N rows to path”; link if file-serving enabled. |
| **filter_dataset** | `dataset_ref`, `rows`, `error?` | “Filtered to N rows; new dataset_ref for downstream.” |
| **sample_dataset** | `dataset_ref`, `rows`, `error?` | “Sampled N rows; new dataset_ref.” |


### Implementation notes

* Image handling is implemented today: formatter reads file at
  `image_path`, base64‑encodes it, and emits Markdown `![alt](data:image/png;base64,...)`.
  (If the file is unavailable it falls back to `Image: <path>`.)
* The formatter lives in `digigraph/formatters/openwebui.py` and is invoked by
  `get_stream_formatter()` when `openwebui_format=True`.
* Unit tests live in `tests/dg/test_openwebui_formatter.py`; they cover
  branching by tool name, JSON parsing of delegate tools, and error formatting.


### Keeping this doc up to date

Whenever a new tool is added or its output keys change, update the relevant
table above and add a corresponding branch in `openwebui.py`.  The tests should
also be extended with a representative payload.

---

*Originally the tool‑specific material lived in `TOOLS_AND_OPENWEBUI.md`; it has
now been merged here.*
