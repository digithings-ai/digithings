/**
 * Curated snapshot of well-known **public remote** MCP servers for the composer
 * `/mcp` id field. Session overlay is a BFF URL fetch — stdio-only servers
 * (filesystem, git, …) do not belong here.
 *
 * This is **not** a live pull from Smithery, PulseMCP, or
 * registry.modelcontextprotocol.io (AGENTS.md human-gates new outbound
 * dependencies). npm packages such as `@getmcp/registry` dump the whole
 * official registry; we keep a short in-repo list instead of that dependency.
 *
 * URLs and auth kinds are copied from vendor docs (snapshot, not a live
 * registry). Re-check the source before adding or changing a row. Skip a
 * popular tool when it has no public remote HTTP/SSE URL.
 */

import { type McpAuthKind, type SessionMcpConfig } from "@/components/stock/embed-mcp-flow";

export const WELL_KNOWN_MCP_GROUPS = [
  "productivity",
  "finance",
  "social",
  "data",
  "infra",
  "chat",
] as const;

export type WellKnownMcpGroup = (typeof WELL_KNOWN_MCP_GROUPS)[number];

/** Empty-id picker: a few per group, not the whole catalog. */
export const WELL_KNOWN_MCP_SUGGEST_PER_GROUP = 3;
export const WELL_KNOWN_MCP_SUGGEST_MAX = 16;

export type WellKnownMcpServer = {
  id: string;
  label: string;
  url: string;
  auth: McpAuthKind;
  group: WellKnownMcpGroup;
};

export const WELL_KNOWN_MCP_SERVERS: readonly WellKnownMcpServer[] = [
  {
    // https://linear.app/docs/mcp
    id: "linear",
    label: "Linear",
    url: "https://mcp.linear.app/mcp",
    auth: "oauth",
    group: "productivity",
  },
  {
    // https://developers.notion.com/guides/mcp/get-started-with-mcp
    id: "notion",
    label: "Notion",
    url: "https://mcp.notion.com/mcp",
    auth: "oauth",
    group: "productivity",
  },
  {
    // https://github.com/atlassian/atlassian-mcp-server — OAuth clients use authv2
    id: "atlassian",
    label: "Atlassian",
    url: "https://mcp.atlassian.com/v1/mcp/authv2",
    auth: "oauth",
    group: "productivity",
  },
  {
    // https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/
    id: "figma",
    label: "Figma",
    url: "https://mcp.figma.com/mcp",
    auth: "oauth",
    group: "productivity",
  },
  {
    // https://developers.asana.com/docs/using-asanas-mcp-server
    id: "asana",
    label: "Asana",
    url: "https://mcp.asana.com/v2/mcp",
    auth: "oauth",
    group: "productivity",
  },
  {
    // https://docs.stripe.com/mcp
    id: "stripe",
    label: "Stripe",
    url: "https://mcp.stripe.com",
    auth: "oauth",
    group: "finance",
  },
  {
    // https://developer.paypal.com/tools/mcp-server/ — Streamable HTTP (not SSE)
    id: "paypal",
    label: "PayPal",
    url: "https://mcp.paypal.com/http",
    auth: "oauth",
    group: "finance",
  },
  {
    // https://developer.squareup.com/docs/mcp
    id: "square",
    label: "Square",
    url: "https://mcp.squareup.com/sse",
    auth: "oauth",
    group: "finance",
  },
  {
    // https://plaid.com/docs/resources/mcp/ — Streamable HTTP; Bearer after OAuth
    id: "plaid",
    label: "Plaid",
    url: "https://api.dashboard.plaid.com/mcp/",
    auth: "oauth",
    group: "finance",
  },
  {
    // https://twelvedata.com/auth.md — hosted MCP, OAuth 2.1
    id: "twelvedata",
    label: "Twelve Data",
    url: "https://mcp.twelvedata.com/mcp",
    auth: "oauth",
    group: "finance",
  },
  {
    // https://docs.coingecko.com/ai-integration/mcp-server — free keyless remote
    id: "coingecko",
    label: "CoinGecko",
    url: "https://mcp.api.coingecko.com/mcp",
    auth: "none",
    group: "finance",
  },
  {
    // https://docs.slack.dev/ai/slack-mcp-server/ — Streamable HTTP
    // No first-party remote MCP for X / Reddit / Bluesky / LinkedIn.
    id: "slack",
    label: "Slack",
    url: "https://mcp.slack.com/mcp",
    auth: "oauth",
    group: "social",
  },
  {
    // https://supabase.com/docs/guides/getting-started/mcp
    id: "supabase",
    label: "Supabase",
    url: "https://mcp.supabase.com/mcp",
    auth: "oauth",
    group: "data",
  },
  {
    // https://github.com/huggingface/hf-mcp-server — PAT in Authorization
    id: "huggingface",
    label: "Hugging Face",
    url: "https://huggingface.co/mcp",
    auth: "bearer",
    group: "data",
  },
  {
    // https://neon.com/docs/ai/neon-mcp-server.md
    id: "neon",
    label: "Neon",
    url: "https://mcp.neon.tech/mcp",
    auth: "oauth",
    group: "data",
  },
  {
    // https://www.prisma.io/docs/postgres/integrations/mcp-server
    id: "prisma",
    label: "Prisma",
    url: "https://mcp.prisma.io/mcp",
    auth: "oauth",
    group: "data",
  },
  {
    // github/github-mcp-server docs/remote-server.md — hosted remote is this
    // URL (OAuth or PAT). Not a Copilot Chat plugin path.
    id: "github",
    label: "GitHub",
    url: "https://api.githubcopilot.com/mcp/",
    auth: "oauth",
    group: "infra",
  },
  {
    // https://docs.sentry.io/product/sentry-mcp/
    id: "sentry",
    label: "Sentry",
    url: "https://mcp.sentry.dev/mcp",
    auth: "oauth",
    group: "infra",
  },
  {
    // https://developers.cloudflare.com/agents/model-context-protocol/mcp-servers-for-cloudflare/
    id: "cloudflare",
    label: "Cloudflare",
    url: "https://mcp.cloudflare.com/mcp",
    auth: "oauth",
    group: "infra",
  },
  {
    // https://vercel.com/docs/mcp/vercel-mcp
    id: "vercel",
    label: "Vercel",
    url: "https://mcp.vercel.com",
    auth: "oauth",
    group: "infra",
  },
  {
    // https://posthog.com/docs/model-context-protocol
    id: "posthog",
    label: "PostHog",
    url: "https://mcp.posthog.com/mcp",
    auth: "oauth",
    group: "infra",
  },
  {
    // https://github.com/upstash/context7 — remote `/mcp` takes an API key;
    // OAuth uses a different `/mcp/oauth` path, so this row stays bearer.
    id: "context7",
    label: "Context7",
    url: "https://mcp.context7.com/mcp",
    auth: "bearer",
    group: "chat",
  },
  {
    // https://docs.devin.ai/work-with-devin/deepwiki-mcp — public, no auth
    id: "deepwiki",
    label: "DeepWiki",
    url: "https://mcp.deepwiki.com/mcp",
    auth: "none",
    group: "chat",
  },
  {
    // https://exa.ai/docs/reference/exa-mcp — hosted search; no key on the free URL
    id: "exa",
    label: "Exa",
    url: "https://mcp.exa.ai/mcp",
    auth: "none",
    group: "chat",
  },
  {
    // https://docs.tavily.com/documentation/mcp — OAuth at this URL (no key in query)
    id: "tavily",
    label: "Tavily",
    url: "https://mcp.tavily.com/mcp/",
    auth: "oauth",
    group: "chat",
  },
  {
    // https://docs.parallel.ai/integrations/mcp/search-mcp — free anonymous search
    id: "parallel",
    label: "Parallel Search",
    url: "https://search.parallel.ai/mcp",
    auth: "none",
    group: "chat",
  },
  {
    // https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server
    id: "gcal",
    label: "Google Calendar",
    url: "https://calendarmcp.googleapis.com/mcp/v1",
    auth: "oauth",
    group: "chat",
  },
  {
    // https://developers.google.com/workspace/gmail/api/guides/configure-mcp-server
    id: "gmail",
    label: "Gmail",
    url: "https://gmailmcp.googleapis.com/mcp/v1",
    auth: "oauth",
    group: "chat",
  },
];

const BY_ID = new Map(WELL_KNOWN_MCP_SERVERS.map((s) => [s.id, s]));

export function isWellKnownMcpGroup(value: string): value is WellKnownMcpGroup {
  return (WELL_KNOWN_MCP_GROUPS as readonly string[]).includes(value);
}

export function wellKnownMcpById(id: string): WellKnownMcpServer | undefined {
  return BY_ID.get(id.trim().toLowerCase());
}

export function wellKnownMcpIds(): readonly string[] {
  return WELL_KNOWN_MCP_SERVERS.map((s) => s.id);
}

export function wellKnownMcpHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

export function filterWellKnownMcps(query: string): WellKnownMcpServer[] {
  const q = query.trim().toLowerCase();
  if (!q) return [...WELL_KNOWN_MCP_SERVERS];
  return WELL_KNOWN_MCP_SERVERS.filter(
    (s) => s.id.includes(q) || s.label.toLowerCase().includes(q),
  );
}

/** Empty query: compact catalog. Typed query: all id/label substring hits. */
export function wellKnownMcpSuggestions(query: string): WellKnownMcpServer[] {
  const q = query.trim().toLowerCase();
  if (q) return filterWellKnownMcps(q);
  const used = new Map<WellKnownMcpGroup, number>();
  const out: WellKnownMcpServer[] = [];
  for (const row of WELL_KNOWN_MCP_SERVERS) {
    const n = used.get(row.group) ?? 0;
    if (n >= WELL_KNOWN_MCP_SUGGEST_PER_GROUP) continue;
    if (out.length >= WELL_KNOWN_MCP_SUGGEST_MAX) break;
    used.set(row.group, n + 1);
    out.push(row);
  }
  return out;
}

export function wellKnownMcpGrouped(
  rows: readonly WellKnownMcpServer[] = WELL_KNOWN_MCP_SERVERS,
): { group: WellKnownMcpGroup; servers: WellKnownMcpServer[] }[] {
  const buckets = new Map<WellKnownMcpGroup, WellKnownMcpServer[]>();
  for (const group of WELL_KNOWN_MCP_GROUPS) buckets.set(group, []);
  for (const row of rows) {
    buckets.get(row.group)?.push(row);
  }
  return WELL_KNOWN_MCP_GROUPS.flatMap((group) => {
    const servers = buckets.get(group) ?? [];
    return servers.length ? [{ group, servers }] : [];
  });
}

/** Catalog autofill for a session MCP draft. Operator id/url stay locked. */
export function applyWellKnownMcp(draft: SessionMcpConfig, rawId: string): SessionMcpConfig {
  if (draft.source === "operator") return draft;
  const id = rawId.trim().toLowerCase();
  const known = wellKnownMcpById(id);
  if (!known) {
    return { ...draft, id };
  }
  const switching = Boolean(draft.id) && draft.id !== known.id;
  return {
    ...draft,
    id: known.id,
    label: known.label,
    url: known.url,
    auth: known.auth,
    token: switching ? "" : draft.token,
  };
}
