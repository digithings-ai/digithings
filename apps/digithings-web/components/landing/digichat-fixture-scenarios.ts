/**
 * Canned MCP turns for the landing-page digichat simulation (#4429, Stage 8).
 *
 * Ported from the design reference's `digichat-fixture-scenarios.ts` with one
 * deliberate subtraction: **the dashboard/quant scenario is not ported.**
 *
 * Why subtract. The reference file also carries a `dashboard` fixture whose
 * canned `digiquant_run_backtest` result contains a fabricated P&L
 * (`total_pnl`, `total_return_pct`, `sharpe_ratio`, `max_drawdown_pct`). The
 * design gallery is a specimen wall and can show that; the marketing site may
 * not — the honesty floor for digithings.ai is that no return, Sharpe or P&L is
 * ever stated for digiquant outside the badged synthetic demo series, and this
 * file is not that series. Interception routes every send to /chat, so the
 * fixture should never run on the landing page at all, but "should never" is
 * not a guarantee worth a fabricated figure. The port therefore keeps only the
 * docs turn, which names tools and paths and states no number.
 *
 * Names, args and results otherwise match the FastMCP tools on digisearch /
 * digivault so a ToolFallback row looks like the live stack.
 */

/** JSON-object args so fixture parts match assistant-ui `ReadonlyJSONObject`. */
export type FixtureToolArgs = {
  readonly [key: string]: string | number | boolean | null;
};

export type FixtureTool = {
  toolCallId: string;
  toolName: string;
  args: FixtureToolArgs;
  argsText: string;
  result: string;
};

export type FixtureScenario = {
  id: "website";
  reasoning: string;
  tools: readonly FixtureTool[];
  reply: string;
};

type WebsiteKind = "digichat" | "modules" | "digigraph" | "search-vault" | "roadmap";

function tool(
  toolCallId: string,
  toolName: string,
  args: FixtureToolArgs,
  result: string,
): FixtureTool {
  return {
    toolCallId,
    toolName,
    args,
    argsText: JSON.stringify(args, null, 2),
    result,
  };
}

function jsonResult(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

/** FastMCP `digisearch_query` returns a formatted string, not JSON. */
function digisearchResult(
  query: string,
  hits: readonly { score: number; path: string; preview: string }[],
): string {
  const blocks = [`Query: ${query}\n---`];
  for (const hit of hits) {
    blocks.push(
      `[score=${hit.score.toFixed(2)}] source=markdown | path=${hit.path}\n${hit.preview}`,
    );
  }
  return blocks.join("\n\n");
}

function vaultNote(args: {
  vault_path: string;
  title: string;
  summary: string;
  body_markdown: string;
  tags?: readonly string[];
}): FixtureTool {
  return tool(
    "dv-1",
    "digivault_get_note",
    { vault_path: args.vault_path, path_prefix: "docs" },
    jsonResult({
      vault_path: args.vault_path,
      title: args.title,
      summary: args.summary,
      tags: args.tags ?? [],
      body_markdown: args.body_markdown,
    }),
  );
}

function websiteKind(prompt: string): WebsiteKind {
  if (/\bmodul/i.test(prompt)) return "modules";
  if (/\b(digigraph|graph|supervisor|orchestrat)\b/i.test(prompt)) return "digigraph";
  if (/\b(digisearch|digivault|vault|retriev|rag)\b/i.test(prompt)) return "search-vault";
  if (/\b(not built|unbuilt|roadmap|planned|unfinished|missing)\b/i.test(prompt)) return "roadmap";
  return "digichat";
}

function websiteScenario(prompt: string): FixtureScenario {
  const kind = websiteKind(prompt);
  const query = prompt.trim() || "digichat";
  const note = WEBSITE_NOTES[kind];
  return {
    id: "website",
    reasoning: WEBSITE_REASONING[kind],
    tools: [
      tool(
        "ds-1",
        "digisearch_query",
        { text: query, index_name: "docs", top_k: 4, mode: "hybrid" },
        digisearchResult(query, note.hits),
      ),
      vaultNote(note.vault),
    ],
    reply: note.reply,
  };
}

const WEBSITE_REASONING: Record<WebsiteKind, string> = {
  digichat: [
    "Docs question on the website embed — retrieve the docs index first.",
    "Then load the matching vault note so the answer cites a real file.",
  ].join("\n"),
  modules: [
    "Portfolio question about how the modules compose, not a product demo.",
    "Search the docs index, then load the note that names the wiring.",
  ].join("\n"),
  digigraph: [
    "Supervisor question — retrieve digigraph architecture from docs.",
    "Load the vault note so the MCP routing is grounded.",
  ].join("\n"),
  "search-vault": [
    "Retrieval vs vault — search both names on the docs index.",
    "Then load the note that explains the locate-then-load loop.",
  ].join("\n"),
  roadmap: [
    "Scope question — the honest answer is what is not shipped.",
    "Search the docs index, then load the roadmap note rather than guessing.",
  ].join("\n"),
};

const WEBSITE_NOTES: Record<
  WebsiteKind,
  {
    hits: { score: number; path: string; preview: string }[];
    vault: {
      vault_path: string;
      title: string;
      summary: string;
      body_markdown: string;
      tags?: readonly string[];
    };
    reply: string;
  }
> = {
  digichat: {
    hits: [
      {
        score: 0.91,
        path: "docs/digichat/README.md",
        preview:
          "digichat is the Next.js BFF + React chat UI on :3005. Marketing /chat is an embed of this process, skinned with chrome.skin: digichat.",
      },
      {
        score: 0.84,
        path: "docs/adr/0018-digichat-path-routing.md",
        preview:
          "Full digichat needs a Node host. The marketing chat uses digichat → digigraph → digillm + the docs corpus.",
      },
    ],
    vault: {
      vault_path: "docs/digichat/README.md",
      title: "digichat",
      summary: "BFF and embed of the product Thread.",
      tags: ["digichat", "embed"],
      body_markdown: [
        "digichat is the chat surface for this stack.",
        "Embeds take chrome.skin, welcome, suggestions, and tools from deploy YAML.",
        "The product Thread is the gallery Thread — not a parallel markdown tree.",
      ].join("\n\n"),
    },
    reply: `**digichat** is the chat surface: a Next.js BFF on \`:3005\`, with the product Thread in the browser.

On **digithings.ai** it is an embed of that process — \`chrome.skin: digichat\`, scoped to the docs index — not a second chat stack. This box on the landing page is the same Thread module, running against canned turns instead of a live container.

A typical docs turn:

1. \`digisearch_query\` — hybrid retrieval over \`index_name: "docs"\`
2. \`digivault_get_note\` — the matching vault page, so citations stay on a real \`vault_path\`
`,
  },
  modules: {
    hits: [
      {
        score: 0.9,
        path: "docs/digigraph/ARCHITECTURE.md",
        preview:
          "digigraph is the LangGraph supervisor. MCP tools on digisearch, digivault, and digiquant are discoverable from one graph.",
      },
      {
        score: 0.85,
        path: "docs/adr/0018-digichat-path-routing.md",
        preview:
          "Every capability is an MCP tool. digichat and the dashboard are two hosts of one graph, not two orchestrators.",
      },
    ],
    vault: {
      vault_path: "docs/digigraph/ARCHITECTURE.md",
      title: "digigraph",
      summary: "The supervisor that discovers every module's tools.",
      tags: ["digigraph", "mcp"],
      body_markdown: [
        "digigraph is the LangGraph supervisor on :8000.",
        "digisearch, digivault and digiquant each expose MCP tools; the graph discovers them.",
        "LiteLLM routes the model calls with caching.",
      ].join("\n\n"),
    },
    reply: `The modules compose through **MCP**, not through import graphs.

- **digigraph** (\`:8000\`) — the LangGraph supervisor. It discovers tools and routes.
- **digisearch** (\`:8002\`) — retrieval over an index you choose.
- **digivault** (\`:8004\`) — the markdown vault those notes live in.
- **digiquant** (\`:8001\`) — NautilusTrader strategies, backtests, portfolio.
- **digikey** (\`:8005\`) — keys, scopes and JWT.
- **digismith** (\`:8003\`) — tracing and the append-only audit log.

Each is a service with its own MCP surface, so removing one narrows the stack instead of breaking it. The supervisor is what makes the loop work: retrieve, then load the full page, then answer.
`,
  },
  digigraph: {
    hits: [
      {
        score: 0.92,
        path: "docs/digigraph/ARCHITECTURE.md",
        preview:
          "digigraph is the LangGraph supervisor. MCP tools on digisearch, digivault, and digiquant are discoverable from one graph.",
      },
      {
        score: 0.81,
        path: "docs/digichat/README.md",
        preview:
          "digichat calls digigraph. The supervisor picks MCP tools; the Thread only renders the calls.",
      },
    ],
    vault: {
      vault_path: "docs/digigraph/ARCHITECTURE.md",
      title: "digigraph",
      summary: "LangGraph supervisor for MCP tools.",
      tags: ["digigraph", "mcp"],
      body_markdown: [
        "digigraph is the LangGraph supervisor on :8000.",
        "MCP tools on digisearch, digivault, and digiquant are discoverable from one graph.",
        "LiteLLM routing with caching. The website embed and the dashboard share this brain.",
      ].join("\n\n"),
    },
    reply: `**digigraph** is the LangGraph supervisor (\`:8000\`). It does not search or backtest itself — it calls MCP tools.

| tool | server |
| --- | --- |
| \`digisearch_query\` | digisearch |
| \`digivault_get_note\` | digivault |
| \`digiquant_list_strategies\` / \`digiquant_run_backtest\` | digiquant |

The website embed and the digiquant dashboard are different **hosts** of the same graph, not two orchestrators.
`,
  },
  "search-vault": {
    hits: [
      {
        score: 0.9,
        path: "docs/digisearch/ARCHITECTURE.md",
        preview:
          "digisearch_query(text, index_name, top_k, mode) returns scored chunks. Hybrid is the default for docs.",
      },
      {
        score: 0.88,
        path: "docs/digivault/ARCHITECTURE.md",
        preview:
          "digivault_get_note loads a note by vault_path (and path_prefix). Use it after retrieval so the model answers from the full page, not a chunk.",
      },
    ],
    vault: {
      vault_path: "docs/digivault/ARCHITECTURE.md",
      title: "digivault",
      summary: "Markdown vault; locate then load.",
      tags: ["digivault", "digisearch"],
      body_markdown: [
        "digisearch is retrieval (chunks, scores, hybrid/keyword/vector).",
        "digivault is the markdown vault those notes live in.",
        "A docs turn is locate (digisearch_query) then load (digivault_get_note with vault_path).",
      ].join("\n\n"),
    },
    reply: `**digisearch** is retrieval. **digivault** is the markdown vault.

They are not aliases:

1. \`digisearch_query\` — \`text\`, \`index_name\`, \`top_k\`, \`mode\` (\`hybrid\` on docs). The result is a scored chunk string, not JSON.
2. \`digivault_get_note\` — \`vault_path\` plus \`path_prefix\`. The result is the note JSON (\`title\`, \`body_markdown\`, …).

Retrieval finds the neighbourhood; the vault load hands the model the whole page. Doing only the first is how a RAG answer ends up quoting half a sentence.
`,
  },
  roadmap: {
    hits: [
      {
        score: 0.89,
        path: "docs/adr/0018-digichat-path-routing.md",
        preview:
          "Hosted MCP surfaces are roadmap. Today the MCP servers are ones you run yourself; there is no public docs endpoint an agent can point at.",
      },
      {
        score: 0.82,
        path: "docs/agents/CODE_REVIEW_POLICY.md",
        preview:
          "Review coverage and merge gates. Anything reaching main was reviewed at its own task pull request.",
      },
    ],
    vault: {
      vault_path: "docs/adr/0018-digichat-path-routing.md",
      title: "what is not built",
      summary: "The honest scope note.",
      tags: ["roadmap", "scope"],
      body_markdown: [
        "Hosted MCP endpoints are roadmap, not shipped — today you run the MCP servers.",
        "Live trading stays behind a human review gate; there is no runtime interlock.",
        "Prices for the integration service are scoped per environment, so none are published.",
      ].join("\n\n"),
    },
    reply: `The honest list:

- **No hosted MCP endpoint.** The MCP servers are ones you run. A public docs endpoint an agent could point at is roadmap, not shipped.
- **No published prices.** The integration service is scoped per environment, so a number before the scope would be a guess dressed as a rate.
- **No runtime interlock on live trading.** That path is guarded by a human review gate, not by software.
- **No closed-weight claim.** The stack works with the providers you already pay for, including open-weight models — but the honest phrasing is "at par or close" on applied work, not "better than the flagships".

Everything else — the supervisor, retrieval, the vault, the keys, the audit log — is in the repository, MIT-licensed, readable without an account.
`,
  },
};

/** Match the prompt to a canned turn. Docs only — see the file header. */
export function pickFixtureScenario(prompt: string): FixtureScenario {
  return websiteScenario(prompt);
}

export function lastUserText(messages: unknown): string {
  if (!Array.isArray(messages)) return "";
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i] as { role?: string; content?: unknown } | undefined;
    if (message?.role !== "user") continue;
    const content = message.content;
    if (typeof content === "string") return content;
    if (!Array.isArray(content)) continue;
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text: unknown }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return "";
}
