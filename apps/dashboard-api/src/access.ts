/**
 * Access manifest — GET /access/manifest (CONTRACT.md §6.x).
 *
 * One policy table answers "which desks, pages, blocks and API routes may this
 * caller see?". Desks are workspaces; a desk lists pages; a page lists blocks;
 * a block binds one GET route. Every node carries a gate (min tier and/or a
 * required group). The dashboard renders sidebar, page guards and locked
 * blocks from this manifest, so entitlements change here and nowhere else.
 *
 * Identity: the worker does no auth itself (no auth/session changes in this
 * slice). The edge in front of it (digikey) injects `x-digi-tier` and
 * `x-digi-groups` (comma-separated); absent or unknown values fail closed to
 * the lowest tier with no groups. These headers are only trustworthy behind
 * that edge — never expose the worker directly with this route enabled.
 */

export type Tier = "free" | "pro" | "max";
const TIER_RANK: Record<Tier, number> = { free: 0, pro: 1, max: 2 };

export interface Caller {
  tier: Tier;
  groups: string[];
}

/** `granted` = usable; `locked` = visible but gated (shows `reason`); hidden nodes are omitted. */
export type Access = "granted" | "locked";

export interface Gate {
  /** Lowest tier that unlocks the node. Default: free. */
  tier?: Tier;
  /** Caller must belong to this group (in addition to the tier). */
  group?: string;
  /** When gated and not met: show as locked (teaser) or omit entirely. Default: locked. */
  hidden?: boolean;
}

interface BlockDef extends Gate { id: string; route: string }
interface PageDef extends Gate { path: string; label: string; status?: "wip" | "soon"; blocks: BlockDef[] }
interface DeskDef extends Gate { id: string; label: string; blurb: string; pages: PageDef[] }

const b = (id: string, route: string, gate: Gate = {}): BlockDef => ({ id, route, ...gate });
const PRO: Gate = { tier: "pro" };

export const DESKS: DeskDef[] = [
  {
    id: "baseline",
    label: "Baseline",
    blurb: "The house pipeline desk: brief, portfolio, pipeline and tools.",
    pages: [
      {
        path: "/brief", label: "Brief",
        blocks: [
          b("brief", "/brief"), b("decision", "/brief"), b("risks", "/brief"),
          b("live", "/kpis/live", PRO), b("performance", "/performance", PRO),
        ],
      },
      {
        path: "/portfolio", label: "Portfolio",
        blocks: [
          b("portfolio", "/portfolio"), b("sleeves", "/allocations"), b("book", "/allocations"),
          b("movers", "/allocations", PRO), b("drawdown", "/performance", PRO), b("nav", "/nav-series", PRO),
          b("benchmarks", "/benchmarks", PRO),
        ],
      },
      { path: "/portfolio/holdings", label: "Holdings", blocks: [b("holdings", "/allocations")] },
      { path: "/portfolio/attribution", label: "Attribution", ...PRO, blocks: [b("attribution", "/attribution")] },
      { path: "/portfolio/ledger", label: "Ledger", ...PRO, blocks: [b("ledger", "/ledger"), b("cash", "/ledger/cash")] },
      { path: "/portfolio/tearsheet", label: "Tearsheet", ...PRO, blocks: [b("performance", "/performance"), b("navtable", "/nav-series"), b("benchmarks", "/benchmarks")] },
      { path: "/portfolio/theses", label: "Theses", blocks: [b("theses", "/theses"), b("signals", "/theses?needs_resolution=1", PRO)] },
      {
        path: "/pipeline", label: "Pipeline",
        blocks: [
          b("pl-run-health", "/pipeline/runs/latest/health"), b("pl-narrative", "/pipeline/runs/latest/narrative"),
          b("pl-canvas", "/pipeline/runs/latest/graph", PRO), b("pl-node-document", "/pipeline/runs/latest/nodes/selected/document", PRO),
          b("pl-call-trace", "/pipeline/runs/latest/trace", PRO), b("pl-artifacts", "/pipeline/runs/latest/artifacts", PRO),
        ],
      },
      { path: "/strategies", label: "Strategies", status: "wip", ...PRO, blocks: [b("st-kpis", "/strategies/summary"), b("st-catalog", "/strategies"), b("st-deployments", "/strategies/deployments")] },
      { path: "/strategies/detail", label: "Detail", status: "wip", ...PRO, blocks: [b("st-overview", "/strategies/default"), b("st-parameters", "/strategies/default/parameters"), b("st-track-record", "/strategies/default/performance"), b("st-runs", "/strategies/default/runs")] },
      { path: "/strategies/deploy", label: "Deploy", status: "wip", tier: "max", blocks: [b("st-targets", "/strategies/targets"), b("st-deploy-flow", "/strategies/deploy-flow"), b("st-deploy-draft", "/strategies/default/deploy-draft")] },
      { path: "/tools/charts", label: "Charts", status: "wip", ...PRO, blocks: [b("mk-price-pane", "/charts/series"), b("mk-chart-series", "/charts/series")] },
      { path: "/tools/chat", label: "digichat", status: "wip", ...PRO, blocks: [b("ch-sessions", "/chat/sessions"), b("ch-thread", "/chat/sessions/current"), b("ch-composer", "/chat/sessions/current")] },
      { path: "/settings", label: "Settings", blocks: [b("se-prefs", "/settings/prefs"), b("se-desk", "/settings/desk")] },
      { path: "/settings/paper", label: "Paper", ...PRO, blocks: [b("se-brokers", "/settings/brokers")] },
    ],
  },
  {
    id: "fx",
    label: "FX Hub",
    blurb: "FX ideas, levels and rates. Invite-only (12x group).",
    group: "12x",
    pages: [
      { path: "/fx", label: "FX Hub", status: "soon", blocks: [b("fx-summary", "/fx/summary"), b("fx-pairs", "/fx/pairs"), b("fx-levels", "/fx/levels"), b("fx-pair-path", "/fx/pairs/{pair}/path"), b("fx-sessions", "/fx/sessions")] },
      { path: "/fx/ideas", label: "Ideas", blocks: [b("fx-ideas", "/fx/ideas"), b("fx-idea-detail", "/fx/ideas/{pair}"), b("fx-flags", "/fx/flags/{pair}"), b("fx-pair-path", "/fx/pairs/{pair}/path")] },
      { path: "/fx/watch", label: "Watch", blocks: [b("fx-pairs", "/fx/pairs"), b("fx-levels", "/fx/levels"), b("fx-paper-exposure", "/fx/paper-exposure"), b("fx-flags", "/fx/flags/{pair}")] },
      { path: "/fx/rates", label: "Rates", blocks: [b("rt-summary", "/rates/summary"), b("rt-curve", "/rates/curve"), b("rt-watchlist", "/rates/watchlist"), b("rt-theses", "/theses?desk=rates")] },
      { path: "/fx/settings", label: "Settings", blocks: [b("se-fx-feed", "/settings/fx-feed"), b("fx-directives", "/fx/directives"), b("se-brokers", "/settings/brokers")] },
    ],
  },
];

export interface BlockEntry { id: string; route: string; access: Access; reason?: string }
export interface PageEntry { path: string; label: string; status?: "wip" | "soon"; access: Access; reason?: string; blocks: BlockEntry[] }
export interface DeskEntry { id: string; label: string; blurb: string; access: Access; reason?: string; pages: PageEntry[] }
export interface Manifest { caller: Caller; desks: DeskEntry[] }

const isTier = (v: string): v is Tier => v === "free" || v === "pro" || v === "max";

/**
 * Local-dev impersonation (`DASHBOARD_DEV_CALLER=max+12x` in .dev.vars): used only
 * when the request carries no identity headers at all. Never set it on a deployed worker.
 */
export function devCaller(spec: string | undefined): Caller | null {
  if (!spec) return null;
  const parts = spec.split("+").map((s) => s.trim().toLowerCase()).filter(Boolean);
  const tier = parts.find(isTier) ?? "free";
  return { tier, groups: parts.filter((p) => !isTier(p)) };
}

/** Caller for a request: edge headers win; else the dev override; else fail closed. */
export function callerFor(request: Request, env: { DASHBOARD_DEV_CALLER?: string }): Caller {
  const h = request.headers;
  if (h.get("x-digi-tier") === null && h.get("x-digi-groups") === null) return devCaller(env.DASHBOARD_DEV_CALLER) ?? parseCaller(h);
  return parseCaller(h);
}

/** Fail closed: unknown/absent tier → free, no groups. */
export function parseCaller(headers: { get(name: string): string | null }): Caller {
  const t = (headers.get("x-digi-tier") ?? "").trim().toLowerCase();
  const groups = (headers.get("x-digi-groups") ?? "").split(",").map((g) => g.trim().toLowerCase()).filter(Boolean);
  return { tier: isTier(t) ? t : "free", groups };
}

/** Why a gate is not met, or null when it is. */
function denial(gate: Gate, c: Caller): string | null {
  if (gate.group && !c.groups.includes(gate.group)) return `Requires the ${gate.group} group`;
  if (gate.tier && TIER_RANK[c.tier] < TIER_RANK[gate.tier]) return `Requires ${gate.tier}`;
  return null;
}

/**
 * Resolve the catalog for one caller. A node is a child of its parent's gate:
 * a locked desk locks every page, a locked page locks every block. Hidden-gated
 * nodes the caller fails are omitted; everything else is shown, granted or locked.
 */
export function buildManifest(c: Caller, desks: DeskDef[] = DESKS): Manifest {
  const out: DeskEntry[] = [];
  for (const d of desks) {
    const dWhy = denial(d, c);
    if (dWhy && d.hidden) continue;
    const pages: PageEntry[] = [];
    for (const p of d.pages) {
      const pWhy = dWhy ?? denial(p, c);
      if (pWhy && p.hidden) continue;
      const blocks: BlockEntry[] = [];
      for (const k of p.blocks) {
        const kWhy = pWhy ?? denial(k, c);
        if (kWhy && k.hidden) continue;
        blocks.push({ id: k.id, route: k.route, access: kWhy ? "locked" : "granted", ...(kWhy ? { reason: kWhy } : {}) });
      }
      pages.push({ path: p.path, label: p.label, ...(p.status ? { status: p.status } : {}), access: pWhy ? "locked" : "granted", ...(pWhy ? { reason: pWhy } : {}), blocks });
    }
    out.push({ id: d.id, label: d.label, blurb: d.blurb, access: dWhy ? "locked" : "granted", ...(dWhy ? { reason: dWhy } : {}), pages });
  }
  return { caller: c, desks: out };
}

/** The data routes this caller may actually call (granted blocks, de-duplicated). */
export function grantedRoutes(m: Manifest): string[] {
  const set = new Set<string>();
  for (const d of m.desks) for (const p of d.pages) for (const k of p.blocks) if (k.access === "granted") set.add(k.route.split("?")[0]);
  return [...set].sort();
}

/** Every route the catalog governs (granted or not), query strings stripped. */
export function governedRoutes(desks: DeskDef[] = DESKS): string[] {
  const set = new Set<string>();
  for (const d of desks) for (const p of d.pages) for (const k of p.blocks) set.add(k.route.split("?")[0]!);
  return [...set];
}

/** Does a request path match a catalog route? `{pair}`-style segments match any one segment. */
export function routeMatches(route: string, path: string): boolean {
  const a = route.split("/");
  const b = path.split("/");
  return a.length === b.length && a.every((seg, i) => (seg.startsWith("{") && seg.endsWith("}") ? b[i] !== "" : seg === b[i]));
}

/**
 * Data-route gate shared by HTTP and MCP. A route the catalog names is allowed only
 * if some granted block uses it; routes the catalog does not name (healthz, tables)
 * are not this gate's business.
 */
export function routeVerdict(m: Manifest, path: string): "allowed" | "forbidden" | "ungoverned" {
  if (!governedRoutes().some((r) => routeMatches(r, path))) return "ungoverned";
  return m.desks.some((d) => d.pages.some((p) => p.blocks.some((k) => k.access === "granted" && routeMatches(k.route.split("?")[0]!, path)))) ? "allowed" : "forbidden";
}
