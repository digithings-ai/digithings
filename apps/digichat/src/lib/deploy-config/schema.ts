/**
 * digichat deployment config — Zod schema (fail closed).
 *
 * File is canonical; env overlays secrets; DIGICHAT_EMBED_TENANTS hydrates the
 * same shape for migration. Spec: digichat deploy config plan + ARCHITECTURE.md.
 */

import { z } from "zod";
import {
  DEFAULT_LANGUAGE_CODE,
  LANGUAGES,
} from "@/lib/languages";
import { THREAD_SKINS, DEFAULT_THREAD_SKIN } from "@/lib/thread-skins";
import {
  DEFAULT_THINKING_MODE,
  DEFAULT_VIEW_MODE,
  THINKING_MODES,
  VIEW_MODES,
} from "@/lib/view-modes";

const SLUG = /^[a-z0-9][a-z0-9-]*$/;
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const LANGUAGE_CODES = new Set(LANGUAGES.map((l) => l.code));

export const ChromeModeSchema = z.enum(["app", "embed", "modal", "sidebar"]);
export const PersistenceSchema = z.enum(["none", "memory", "server"]);
export const AuthModeSchema = z.enum(["anonymous", "session"]);
export const ThemeSchema = z.enum(["dark", "light"]);
export const ThreadSkinSchema = z.enum(THREAD_SKINS);
const ThreadSkinInputSchema = z.preprocess(
  (value) => (typeof value === "string" ? value.trim().toLowerCase() : value),
  ThreadSkinSchema,
);
export const GateModeSchema = z.enum(["turn_limited", "ungated", "trial_form"]);
export const ActivityDetailSchema = z.enum(["off", "labels", "full"]);
/**
 * Host-page context injection from the popup widget (`digichat:page-context`):
 * - `off` — ignore incoming page-context messages entirely (no listener).
 * - `silent` — the snapshot still reaches the model, but no attachment chip.
 * - `visible` — current behavior: chip in composer and sent message.
 * Deployment-configured; parents see the mode on `digichat:ready`.
 */
export const PageContextModeSchema = z.enum(["off", "silent", "visible"]);
export const LlmAccessSchema = z.enum([
  "free_then_byok",
  "byok_only",
  "backend_only",
  "operator",
]);
export const UserAlignSchema = z.enum(["right", "left"]);

const WelcomeBodySchema = z.union([
  z.string().min(1),
  z.array(z.string().min(1)).min(1),
]);

/** Empty-state copy. A bare string still means title-only (legacy YAML). */
export const WelcomeCopySchema = z
  .object({
    title: z.string().min(1),
    body: WelcomeBodySchema.optional(),
  })
  .strict();

export type WelcomeCopy = z.infer<typeof WelcomeCopySchema>;

export function coerceWelcomeCopy(value: unknown): unknown {
  if (value == null || value === "") return undefined;
  if (typeof value === "string") {
    const title = value.trim();
    return title.length > 0 ? { title } : undefined;
  }
  return value;
}

export function parseWelcomeCopy(value: unknown): WelcomeCopy | undefined {
  const coerced = coerceWelcomeCopy(value);
  if (coerced == null) return undefined;
  return WelcomeCopySchema.parse(coerced);
}

export function welcomeTitle(welcome: WelcomeCopy | undefined): string | undefined {
  return welcome?.title;
}

export function welcomeBodyLines(welcome: WelcomeCopy | undefined): string[] {
  if (!welcome?.body) return [];
  return typeof welcome.body === "string" ? [welcome.body] : [...welcome.body];
}

/**
 * Reasoning / tool-call disclosure. Booleans coerce for older YAML:
 * true → collapsed, false → off.
 */
export const DisclosureModeSchema = z.enum([
  "off",
  "collapsed",
  "expanded",
  "locked_open",
]);
export type DisclosureMode = z.infer<typeof DisclosureModeSchema>;

/** Chain-of-thought view mode (reasoning + tool calls). See view-modes.ts. */
export const ViewModeSchema = z.enum(VIEW_MODES);
/** Reasoning-only override on top of the view mode. */
export const ThinkingModeSchema = z.enum(THINKING_MODES);

export const AccentSchema = z.object({
  color: z.string().regex(HEX_COLOR, "must be #rrggbb"),
  foreground: z.string().regex(HEX_COLOR, "must be #rrggbb"),
});

export const LauncherSchema = z
  .object({
    hotkey: z.string().min(1).optional(),
    mobileFullscreen: z.boolean().optional(),
    label: z.string().optional(),
    closeLabel: z.string().optional(),
    /** widget.js / dashboard popup chrome: rectangular bar vs legacy dot */
    mode: z.enum(["dot", "bar"]).optional(),
  })
  .strict();

export const TranscriptSchema = z
  .object({
    /** User bubble alignment — stock web default is right. */
    userAlign: UserAlignSchema.default("right"),
  })
  .strict();

export const ChromeSchema = z
  .object({
    mode: ChromeModeSchema.default("embed"),
    theme: ThemeSchema.default("light"),
    /**
     * Which Thread to mount (11 official catalog ids + first-party `digichat`).
     * Overlay: `DIGICHAT_CHROME_SKIN`. Catalog default remains `base`.
     * First-party hosts default omitted `skin` to `digichat` in the tenants
     * parser (`defaultThreadSkinForTenant`).
     */
    skin: ThreadSkinInputSchema.default(DEFAULT_THREAD_SKIN),
    launcher: LauncherSchema.optional(),
    title: z.string().optional(),
    welcome: z.preprocess(coerceWelcomeCopy, WelcomeCopySchema.optional()),
    suggestions: z.array(z.string()).optional(),
    placeholder: z.string().optional(),
    accent: AccentSchema.optional(),
    attribution: z.boolean().optional(),
    /** Curated reply-language default (see languages.ts). */
    defaultLanguage: z
      .string()
      .refine((c) => LANGUAGE_CODES.has(c), "unknown language code")
      .default(DEFAULT_LANGUAGE_CODE),
    transcript: TranscriptSchema.default({ userAlign: "right" }),
  })
  .strict();

/**
 * Legacy `features.reasoning` / `features.toolCalls` disclosure keys fold
 * forward onto the view-mode pair so older YAML keeps loading. Per-field:
 * a new-style value always wins; a legacy value maps to the closest mode
 * (toolCalls off→hidden / expanded→detailed / collapsed→compact; reasoning
 * expanded→thinking open, anything else→pinned collapsed).
 */
function foldLegacyDisclosure(value: unknown): unknown {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    return value;
  }
  const record = { ...(value as Record<string, unknown>) };
  const toolCalls = record.toolCalls;
  const reasoning = record.reasoning;
  delete record.toolCalls;
  delete record.reasoning;
  if (record.view == null && toolCalls !== undefined) {
    record.view =
      toolCalls === false || toolCalls === "off"
        ? "hidden"
        : toolCalls === "expanded" || toolCalls === "locked_open"
          ? "detailed"
          : "compact";
  }
  if (record.thinking == null && reasoning !== undefined) {
    record.thinking =
      reasoning === "expanded" || reasoning === "locked_open"
        ? "open"
        : "collapsed";
  }
  return record;
}

export const FeaturesSchema = z.preprocess(
  foldLegacyDisclosure,
  z
    .object({
      attachments: z.boolean().default(true),
      dictation: z.boolean().default(false),
      speech: z.boolean().default(false),
      /** Chain-of-thought disclosure for reasoning + tool calls. */
      view: ViewModeSchema.default(DEFAULT_VIEW_MODE),
      /** Reasoning-only override on top of `view`. */
      thinking: ThinkingModeSchema.default(DEFAULT_THINKING_MODE),
      sources: z.boolean().default(true),
      /**
       * Legacy alias for `models.allowPicker` (#4532). Kept for config
       * back-compat: the client projection folds it into `models.allowPicker`,
       * which is the authoritative client-facing knob. Prefer
       * `models.allowPicker` in new configs.
       */
      modelPicker: z.boolean().default(false),
      branchPicker: z.boolean().default(true),
      pageContext: PageContextModeSchema.default("visible"),
    })
    .strict(),
);

export const ModelsSchema = z
  .object({
    default: z.string().min(1).optional(),
    available: z.array(z.string().min(1)).default([]),
    /**
     * Authoritative client-facing model-picker switch (#4532). The legacy
     * `features.modelPicker` alias is folded into this during projection.
     */
    allowPicker: z.boolean().optional(),
  })
  .strict();

export const CliSchema = z
  .object({
    /**
     * When true, this install is expected to ship/run the digichat Ink CLI
     * against this BFF. Advisory for operators; the web app never imports Ink.
     */
    enabled: z.boolean().default(false),
  })
  .strict();

export const DigigraphBackendSchema = z
  .object({
    type: z.literal("digigraph"),
    digisearchIndex: z.string().min(1).optional(),
    vaultPathPrefix: z.string().min(1).optional(),
  })
  .strict();

export const FoundryBackendSchema = z
  .object({
    type: z.literal("foundry"),
    projectEndpoint: z
      .string()
      .url()
      .refine((u) => u.startsWith("https:"), "projectEndpoint must be https"),
    agentName: z.string().min(1),
  })
  .strict();

/**
 * An OpenAI-compatible endpoint reached through the AI SDK (#4535).
 *
 * `apiKeyEnv` NAMES an env var; the key itself never lives in the config, so
 * it cannot be projected to the browser. The `DIGICHAT_BACKEND_` prefix is
 * enforced so a tenant config can never point at `AUTH_SECRET`,
 * `DIGIKEY_BFF_TOKEN`, or `DIGIGRAPH_UPSTREAM_API_KEY` and have the BFF send
 * that secret as a Bearer token to an attacker-controlled `baseUrl`. It bounds
 * *which* vars are nameable; it does not bind an entry to its own key (every
 * config source is operator-controlled today — add a per-entry binding such as
 * `DIGICHAT_BACKEND_<SLUG>_KEY` if tenant-authored config is ever accepted).
 * https-only keeps the key from crossing the wire in plaintext, matching
 * `FoundryBackendSchema`'s `projectEndpoint` rule.
 */
const OpenAiCompatibleFields = {
  baseUrl: z
    .string()
    .url()
    .refine((u) => u.startsWith("https:"), "baseUrl must be https"),
  model: z.string().min(1),
  apiKeyEnv: z
    .string()
    .regex(
      /^DIGICHAT_BACKEND_[A-Z0-9_]+$/,
      "apiKeyEnv must name a DIGICHAT_BACKEND_* env var",
    ),
};

/** OpenAI Chat Completions wire format (`/v1/chat/completions`). */
export const OpenAiCompletionsBackendSchema = z
  .object({
    type: z.literal("openai-completions"),
    ...OpenAiCompatibleFields,
  })
  .strict();

/** OpenAI Responses wire format (`/v1/responses`). */
export const OpenAiResponsesBackendSchema = z
  .object({
    type: z.literal("openai-responses"),
    ...OpenAiCompatibleFields,
  })
  .strict();

/**
 * Anthropic Messages API reached through the AI SDK (#4539).
 *
 * `apiKeyEnv` NAMES an env var with the same `DIGICHAT_BACKEND_` guard as the
 * OpenAI pair, so a tenant config can never have the BFF ship `AUTH_SECRET` to
 * a provider. There is no `baseUrl`: the provider defaults to
 * `https://api.anthropic.com` — point a proxy at `openai-completions` instead.
 */
export const AnthropicBackendSchema = z
  .object({
    type: z.literal("anthropic"),
    model: z.string().min(1),
    apiKeyEnv: z
      .string()
      .regex(
        /^DIGICHAT_BACKEND_[A-Z0-9_]+$/,
        "apiKeyEnv must name a DIGICHAT_BACKEND_* env var",
      ),
  })
  .strict();

/**
 * Google Vertex AI (Gemini) reached through the AI SDK (#4539).
 *
 * No credential field: the provider reads Application Default Credentials from
 * the ambient environment (`google-auth-library`), so nothing secret is ever
 * expressible in — or projectable from — the config.
 *
 * `project` / `location` therefore select which GCP project the BFF's ambient
 * (cloud-platform scoped) credential is spent against. Config sources are
 * operator-controlled today, so this is an authorization-scope note rather than
 * a tenant-facing risk; add an allowlist here if tenant-authored config is ever
 * accepted.
 */
export const GoogleVertexBackendSchema = z
  .object({
    type: z.literal("google-vertex"),
    project: z.string().min(1),
    location: z.string().min(1),
    model: z.string().min(1),
  })
  .strict();

/**
 * Non-AI-SDK protocol backends (#4543). Each is a stream the BFF consumes and
 * normalizes itself, so there is no provider package behind them.
 *
 * All three take an OPTIONAL `apiKeyEnv` naming an env var (same
 * `DIGICHAT_BACKEND_` prefix guard as the OpenAI pair, so a tenant config can
 * never name `AUTH_SECRET`). LangGraph Cloud wants the key in `x-api-key`; a
 * private AG-UI or A2A server usually wants a bearer. https-only URLs keep the
 * credential off the wire in plaintext, matching the other backend types.
 */
const HttpsBackendUrl = z
  .string()
  .url()
  .refine((u) => u.startsWith("https:"), "must be https");

const OptionalBackendApiKeyEnv = z
  .string()
  .regex(/^DIGICHAT_BACKEND_[A-Z0-9_]+$/, "apiKeyEnv must name a DIGICHAT_BACKEND_* env var");

/** LangGraph Platform `runs/stream` (stateless run, no thread management). */
export const LangGraphBackendSchema = z
  .object({
    type: z.literal("langgraph"),
    apiUrl: HttpsBackendUrl,
    assistantId: z.string().min(1),
    apiKeyEnv: OptionalBackendApiKeyEnv.optional(),
  })
  .strict();

/** AG-UI event stream (`POST {url}`, SSE frames with a `type` discriminator). */
export const AgUiBackendSchema = z
  .object({
    type: z.literal("ag-ui"),
    url: HttpsBackendUrl,
    apiKeyEnv: OptionalBackendApiKeyEnv.optional(),
  })
  .strict();

/** A2A JSON-RPC 2.0 endpoint (`message/stream`, or a blocking `message/send`). */
export const A2aBackendSchema = z
  .object({
    type: z.literal("a2a"),
    baseUrl: HttpsBackendUrl,
    apiKeyEnv: OptionalBackendApiKeyEnv.optional(),
  })
  .strict();

export const BackendSchema = z.discriminatedUnion("type", [
  DigigraphBackendSchema,
  FoundryBackendSchema,
  OpenAiCompletionsBackendSchema,
  OpenAiResponsesBackendSchema,
  AnthropicBackendSchema,
  GoogleVertexBackendSchema,
  LangGraphBackendSchema,
  AgUiBackendSchema,
  A2aBackendSchema,
]);

export const ToolCatalogEntrySchema = z
  .object({
    id: z.string().min(1),
    default: z.boolean().optional(),
    label: z.string().optional(),
  })
  .strict();

export const ToolsSchema = z
  .object({
    allowUserToggle: z.boolean().default(true),
    catalog: z.array(ToolCatalogEntrySchema).default([]),
  })
  .strict();

export const McpServerSchema = z
  .object({
    id: z
      .string()
      .regex(/^[a-z0-9][a-z0-9-]{0,63}$/, "mcp server id must be a lowercase slug without underscores"),
    /** BFF-only URL — never projected to the browser */
    url: z.string().url(),
    label: z.string().optional(),
    default: z.boolean().optional(),
    /**
     * Operator-static secret for this server (e.g. a per-tenant MCP API
     * key). Never client-projected (#3841). Prefer `tokenEnv` over inlining
     * this directly in checked-in YAML.
     */
    token: z.string().optional(),
    /**
     * Name of the env var to resolve `token` from at load time (mirrors the
     * deployment-level `DIGICHAT_EMBED_TOKEN` pattern). Loader fills `token`
     * from this when `token` is unset (#3841).
     */
    tokenEnv: z.string().optional(),
    /**
     * MCP setup values applied when this server's tools are registered (e.g.
     * the digisearch index name or the digivault path prefix). Forwarded
     * verbatim to digigraph; the model never sees or supplies them.
     */
    setup: z.record(z.string(), z.string()).optional(),
    /**
     * Custom outbound header name for the resolved token, e.g. "X-API-Key".
     * Defaults to `Authorization: Bearer <token>` when unset. Operator-only —
     * the session overlay (user-supplied auth) cannot set this (#3841).
     */
    authHeader: z
      .string()
      .regex(/^[A-Za-z][A-Za-z0-9-]{0,40}$/, "authHeader must be a valid HTTP header name")
      .optional(),
  })
  .strict();

export const McpSchema = z
  .object({
    servers: z.array(McpServerSchema).default([]),
    /**
     * Session overlay switch: when true, `/mcp new` URLs that pass
     * `isAllowedMcpServerUrl` are merged into the upstream MCP header.
     * Operator YAML URLs stay server-side. Default false on public embeds.
     */
    allowUserServers: z.boolean().default(false),
    /** Show the add-custom-server form. Ignored unless allowUserServers. */
    allowAddForm: z.boolean().default(false),
  })
  .strict();

export const GateSchema = z
  .object({
    mode: GateModeSchema.default("ungated"),
    activityDetail: ActivityDetailSchema.default("labels"),
    llmAccess: LlmAccessSchema.optional(),
    /** Server-side quota consume — never client-projected */
    consumeUrl: z
      .string()
      .url()
      .refine((u) => u.startsWith("https:"), "consumeUrl must be https")
      .optional(),
    lockedContact: z.string().optional(),
    showByok: z.boolean().optional(),
    showLanguageSelector: z.boolean().optional(),
    /** Legacy embed field — also implies tools.catalog web_search when true */
    webSearch: z.boolean().optional(),
    /**
     * Minimum Desk+ plan for this embed. Server-only (#3662 HMAC X-Embed-Plan-Proof).
     * Never projected to the browser.
     */
    requiredPlanTier: z.enum(["desk", "studio", "enterprise"]).optional(),
  })
  .strict();

export const DeploymentSchema = z
  .object({
    slug: z.string().regex(SLUG, "slug must be lowercase alphanumeric/hyphens"),
    aliases: z.array(z.string()).optional(),
    chrome: ChromeSchema.default({
      mode: "embed",
      theme: "light",
      skin: DEFAULT_THREAD_SKIN,
      defaultLanguage: DEFAULT_LANGUAGE_CODE,
      transcript: { userAlign: "right" },
    }),
    persistence: PersistenceSchema.default("none"),
    auth: AuthModeSchema.default("anonymous"),
    features: FeaturesSchema.default({
      attachments: true,
      dictation: false,
      speech: false,
      view: DEFAULT_VIEW_MODE,
      thinking: DEFAULT_THINKING_MODE,
      sources: true,
      modelPicker: false,
      branchPicker: true,
      pageContext: "visible",
    }),
    models: ModelsSchema.default({ available: [] }),
    cli: CliSchema.default({ enabled: false }),
    backend: BackendSchema,
    tools: ToolsSchema.optional(),
    mcp: McpSchema.optional(),
    gate: GateSchema.default({ mode: "ungated", activityDetail: "labels" }),
    /**
     * Embed token (X-Embed-Token). Required for non-first-party hosts.
     * Never projected to the browser via the client config API.
     */
    token: z.string().min(1).optional(),
  })
  .strict();

export const DigichatConfigSchema = z
  .object({
    version: z.literal(1),
    /** Single-install product shape (typical client deploy). */
    deployment: DeploymentSchema.optional(),
    /**
     * Multi-host registry (digithings’ own container serving digithings.ai + OCC).
     * Keys are hostnames / origins; aliases may also be listed on each entry.
     */
    hosts: z.record(z.string(), DeploymentSchema).optional(),
  })
  .strict()
  .superRefine((val, ctx) => {
    if (!val.deployment && (!val.hosts || Object.keys(val.hosts).length === 0)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "digichat config requires deployment or at least one hosts entry",
      });
    }
  });

export type ChromeMode = z.infer<typeof ChromeModeSchema>;
export type ThreadSkin = z.infer<typeof ThreadSkinSchema>;
export type PersistenceMode = z.infer<typeof PersistenceSchema>;
export type AuthMode = z.infer<typeof AuthModeSchema>;
export type UserAlign = z.infer<typeof UserAlignSchema>;
export type PageContextMode = z.infer<typeof PageContextModeSchema>;
export type DigichatDeployment = z.infer<typeof DeploymentSchema>;
export type DigichatConfig = z.infer<typeof DigichatConfigSchema>;
export type ToolCatalogEntry = z.infer<typeof ToolCatalogEntrySchema>;

/** Visible (not off) disclosure modes. */
export function disclosureIsVisible(mode: DisclosureMode): boolean {
  return mode !== "off";
}

/** defaultOpen for collapsible reasoning/tool UI. */
export function disclosureDefaultOpen(mode: DisclosureMode): boolean {
  return mode === "expanded" || mode === "locked_open";
}

/** Collapse control disabled when locked open. */
export function disclosureIsLocked(mode: DisclosureMode): boolean {
  return mode === "locked_open";
}

/**
 * Fail-closed model allowlist when `available` is non-empty.
 * Empty `available` → no restriction (requested or `default`).
 * Non-empty list → requested must be listed; missing request uses `default`
 * if listed, else first available entry.
 */
export function allowlistModelId(
  models: DigichatDeployment["models"] | undefined,
  requested: string | null | undefined,
): string | undefined {
  const id = requested?.trim() || undefined;
  const available = models?.available ?? [];
  if (available.length === 0) {
    return id ?? models?.default;
  }
  if (!id) {
    if (models?.default && available.includes(models.default)) {
      return models.default;
    }
    return available[0];
  }
  return available.includes(id) ? id : undefined;
}

/** Parse + validate unknown JSON/YAML object. Throws on failure (fail closed). */
export function parseDigichatConfig(input: unknown, ctx = "digichat config"): DigichatConfig {
  const result = DigichatConfigSchema.safeParse(input);
  if (!result.success) {
    const detail = result.error.issues
      .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
      .join("; ");
    throw new Error(`${ctx}: ${detail}`);
  }
  return result.data;
}
