/** Hand-written declarations for security-headers.mjs. */

export const DEFAULT_DIGICHAT_EMBED_ORIGIN: string;

/** R2-backed market-data Worker origin for the landing price tape's CSP. */
export const DEFAULT_MARKET_DATA_ORIGIN: string;

export function resolveDigichatEmbedOrigin(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string | null;

export function resolveMarketDataOrigin(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string | null;

/** digiquant Supabase origin the landing band's live reads use; null when unset. */
export function resolveSupabaseOrigin(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string | null;

export function frameSrcForCsp(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function marketDataOriginForCsp(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function supabaseOriginForCsp(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string | null;

export function embedOriginForChat(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function digithingsCsp(
  frameSrc?: string,
  marketOrigin?: string,
  supabaseOrigin?: string | null,
): string;

/** CSP for the /openwiki/* visualizer export (#3696). */
export function openwikiCsp(): string;

export function renderCloudflareHeaders(
  frameSrc?: string,
  supabaseOrigin?: string | null,
): string;
