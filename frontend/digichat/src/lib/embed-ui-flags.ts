import type { EmbedTenantClientConfig } from "@/hooks/use-embed-tenant-config";

/** Where the "powered by digichat" credit renders — in at most one place. */
export type AttributionPlacement = "footer" | "header" | "none";

/**
 * Where the credit renders. The two old gates (`headerTitle` for the header
 * parenthetical, `attribution && !headerTitle` for the footer) were already
 * mutually exclusive, so this is not a de-duplication — it changes WHICH place
 * wins for one case, and makes the choice legible in one expression.
 *
 * The footer wins wherever it is available: a quiet line under the transcript
 * reads as a credit, where the same words in parentheses beside the client's
 * own name read as a co-brand, which is not what a white-labelled embed is for.
 *
 * The case that changes is a TITLED tenant with `attribution: true` — it could
 * previously never reach the footer, because that gate excluded any tenant with
 * a title, so opting in did nothing and the parenthetical stayed. Now opting in
 * MOVES the credit down. An untitled opted-in tenant already got the footer and
 * still does. Tenants that never opted in keep the header parenthetical — but
 * only when they set a title, since an untitled embed's header is the digichat
 * wordmark itself and "digichat (by digichat)" says it twice.
 */
export function resolveAttributionPlacement(args: {
  attribution: boolean;
  headerTitle?: string | null;
}): AttributionPlacement {
  if (args.attribution) return "footer";
  return args.headerTitle ? "header" : "none";
}

export function resolveEmbedUiFlags(cfg: EmbedTenantClientConfig): {
  showByok: boolean;
  layout: "page" | "embed";
  showLanguageSelector: boolean;
  webSearch: boolean;
} {
  return {
    showByok: cfg.showByok === true,
    layout: cfg.layout === "page" ? "page" : "embed",
    showLanguageSelector: cfg.showLanguageSelector === true,
    webSearch: cfg.webSearch === true,
  };
}
