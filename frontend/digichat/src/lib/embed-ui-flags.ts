import type { EmbedTenantClientConfig } from "@/hooks/use-embed-tenant-config";

/** Where the "powered by digichat" credit renders — in at most one place. */
export type AttributionPlacement = "footer" | "header" | "none";

/**
 * Attribution appears exactly ONCE. The footer wins wherever it is available:
 * a quiet line under the transcript reads as a credit, where the same words in
 * parentheses beside the client's own name read as a co-brand, which is not
 * what a white-labelled embed is for.
 *
 * `attribution` is the tenant's opt-in, so turning it on MOVES the credit down
 * rather than adding a second one. Tenants that never opted in keep the header
 * parenthetical they have always had — but only when they set a title, since
 * an untitled embed's header is the digichat wordmark itself and "digichat (by
 * digichat)" says it twice.
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
  showStatusBar: boolean;
  layout: "page" | "embed";
} {
  return {
    showByok: cfg.showByok === true,
    showStatusBar: cfg.showStatusBar === true,
    layout: cfg.layout === "page" ? "page" : "embed",
  };
}
