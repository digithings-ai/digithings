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

function coerceDisclosureMode(value: unknown): unknown {
  if (value === true) return "collapsed";
  if (value === false) return "off";
  return value;
}

const DisclosureModeInputSchema = z.preprocess(
  coerceDisclosureMode,
  DisclosureModeSchema,
);

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

export const FeaturesSchema = z
  .object({
    attachments: z.boolean().default(false),
    dictation: z.boolean().default(false),
    speech: z.boolean().default(false),
    reasoning: DisclosureModeInputSchema.default("collapsed"),
    toolCalls: DisclosureModeInputSchema.default("collapsed"),
    sources: z.boolean().default(true),
    modelPicker: z.boolean().default(false),
    branchPicker: z.boolean().default(true),
  })
  .strict();

export const ModelsSchema = z
  .object({
    default: z.string().min(1).optional(),
    available: z.array(z.string().min(1)).default([]),
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

export const BackendSchema = z.discriminatedUnion("type", [
  DigigraphBackendSchema,
  FoundryBackendSchema,
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
      .regex(/^[a-z0-9][a-z0-9_-]{0,63}$/, "mcp server id must be lowercase slug"),
    /** BFF-only URL — never projected to the browser */
    url: z.string().url(),
    label: z.string().optional(),
    default: z.boolean().optional(),
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
      attachments: false,
      dictation: false,
      speech: false,
      reasoning: "collapsed",
      toolCalls: "collapsed",
      sources: true,
      modelPicker: false,
      branchPicker: true,
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
