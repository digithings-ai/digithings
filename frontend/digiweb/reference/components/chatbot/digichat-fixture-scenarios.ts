/**
 * Canned MCP turns for the gallery Thread. Names, args, and results match the
 * FastMCP tools on digisearch / digivault / digiquant so ToolFallback looks
 * like the live stack (website embed and digiquant dashboard).
 */

export type FixtureTool = {
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  argsText: string;
  result: string;
};

export type FixtureScenario = {
  id: "website" | "dashboard";
  reasoning: string;
  tools: readonly FixtureTool[];
  reply: string;
};

type WebsiteKind = "digichat" | "embeds" | "digigraph" | "search-vault";

function tool(
  toolCallId: string,
  toolName: string,
  args: Record<string, unknown>,
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
  if (/\bembed/i.test(prompt)) return "embeds";
  if (/\bdigigraph\b/i.test(prompt)) return "digigraph";
  if (/\b(digisearch|digivault|vault)\b/i.test(prompt)) return "search-vault";
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
  embeds: [
    "This is about the embed path, not a new chat product.",
    "Search the docs index, then open the routing note.",
  ].join("\n"),
  digigraph: [
    "Supervisor question — retrieve digigraph architecture from docs.",
    "Load the vault note so MCP routing is grounded.",
  ].join("\n"),
  "search-vault": [
    "Retrieval vs vault — search both names on the docs index.",
    "Then load the note that explains the locate-then-load loop.",
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
    reply: `**digichat** is the chat surface: Next.js BFF on \`:3005\`, product Thread in the browser.

On **digithings.ai** it is an embed of that process — \`chrome.skin: digichat\`, scoped to the docs index — not a second chat stack.

A typical docs turn:

1. \`digisearch_query\` — hybrid retrieval over \`index_name: "docs"\`
2. \`digivault_get_note\` — the matching vault page, so citations stay on a real \`vault_path\`
`,
  },
  embeds: {
    hits: [
      {
        score: 0.9,
        path: "docs/adr/0018-digichat-path-routing.md",
        preview:
          "Embeds are one process, many routes. chrome.skin, welcome, and tools come from deploy YAML. DigichatLauncher is the square-to-panel host; the iframe is still digichat.",
      },
      {
        score: 0.86,
        path: "docs/digichat/README.md",
        preview:
          "Marketing /chat is an embed of the digichat process. Popup and page chat share the Thread; layout compact is attach · field · send on one row.",
      },
    ],
    vault: {
      vault_path: "docs/adr/0018-digichat-path-routing.md",
      title: "digichat path routing",
      summary: "One process, many embed routes.",
      tags: ["digichat", "embed"],
      body_markdown: [
        "Full digichat needs a Node host.",
        "Embeds take chrome.skin, welcome, suggestions, and tools from deploy YAML.",
        "DigichatLauncher portals a compact Thread; it is not a new Container per chat.",
      ].join("\n\n"),
    },
    reply: `Embeds are **one digichat process**, many routes — not a new container per page.

- Host: \`DigichatLauncher\` (30px square → panel)
- Frame: the same product Thread, \`chrome.skin\` / welcome / tools from deploy YAML
- Website marketing chat is \`chrome.skin: digichat\` over the docs index

Popup composer is the compact layout (attach · field · send on one row). The iframe is still digichat, not a parallel markdown tree.
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

1. \`digisearch_query\` — \`text\`, \`index_name\`, \`top_k\`, \`mode\` (\`hybrid\` on docs). Result is a scored chunk string, not JSON.
2. \`digivault_get_note\` — \`vault_path\` + \`path_prefix\`. Result is the note JSON (\`title\`, \`body_markdown\`, …).

Do not pass a digisearch \`path\` straight in as \`vault_path\` on a D1 tenant; the gallery docs corpus uses repo paths that the vault can load.
`,
  },
};

function dashboardSymbol(prompt: string): string {
  if (/\b(btc[-]?usd|bitcoin)\b/i.test(prompt)) return "BTC-USD";
  if (/\b(sol[-]?usd|solana)\b/i.test(prompt)) return "SOL-USD";
  return "ETH-USD";
}

function dashboardScenario(prompt: string): FixtureScenario {
  const symbol = dashboardSymbol(prompt);
  const params = { kelly: 0.5 };
  const backtest = {
    run_id: `bt-trend-xsec-${symbol.toLowerCase()}-001`,
    strategy_name: "trend_xsec",
    symbols: [symbol],
    start_time: "2018-01-01T00:00:00Z",
    end_time: "2026-01-01T00:00:00Z",
    total_pnl: 18420.55,
    total_return_pct: 142.3,
    sharpe_ratio: 1.18,
    max_drawdown_pct: -18.4,
    num_trades: 146,
    per_symbol_pnl: { [symbol]: 18420.55 },
    status: "ok",
    message: "",
  };
  return {
    id: "dashboard",
    reasoning: [
      "Operator surface — this is a digiquant dashboard turn, not a docs question.",
      "List registered strategies, then run the named one through Nautilus.",
    ].join("\n"),
    tools: [
      tool(
        "dq-1",
        "digiquant_list_strategies",
        {},
        jsonResult([
          {
            name: "trend_xsec",
            aliases: ["trend"],
            description: "Cross-sectional / time-series trend",
            default_params: { kelly: 0.5 },
          },
          {
            name: "macd_trend",
            aliases: [],
            description: "MACD trend-following strategy",
            default_params: {
              trade_size: 1000,
              fast_period: 12,
              slow_period: 26,
              signal_period: 9,
            },
          },
          {
            name: "bollinger_mr",
            aliases: ["mean_reversion_stat_arb", "mr"],
            description: "Bollinger mean-reversion",
            default_params: {},
          },
        ]),
      ),
      tool(
        "dq-2",
        "digiquant_run_backtest",
        {
          strategy_name: "trend_xsec",
          symbols_json: JSON.stringify([symbol]),
          strategy_params_json: JSON.stringify(params),
        },
        jsonResult(backtest),
      ),
    ],
    reply: `Backtest finished on the dashboard path — Nautilus via \`digiquant_run_backtest\`.

| metric | value |
| --- | --- |
| strategy | trend_xsec |
| symbol | ${symbol} |
| total return | **${backtest.total_return_pct}%** |
| Sharpe | ${backtest.sharpe_ratio} |
| max DD | ${backtest.max_drawdown_pct}% |
| trades | ${backtest.num_trades} |
| PnL | ${backtest.total_pnl} |

Kelly cap 0.5× in \`strategy_params_json\`. Same MCP tools the operator graph calls from the digiquant dashboard embed — not a docs retrieval.
`,
  };
}

const QUANT_HINT =
  /\b(backtest|eth-?usd|btc-?usd|sol-?usd|trend_xsec|tearsheet|optimize|nautilus|dashboard|kelly|drawdown|sharpe)\b/i;

export function pickFixtureScenario(prompt: string): FixtureScenario {
  return QUANT_HINT.test(prompt) ? dashboardScenario(prompt) : websiteScenario(prompt);
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
