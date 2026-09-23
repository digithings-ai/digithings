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

export function frameSrcForCsp(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function marketDataOriginForCsp(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function embedOriginForChat(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function digithingsCsp(frameSrc?: string, marketOrigin?: string): string;

/** CSP for the /openwiki/* visualizer export (#3696). */
export function openwikiCsp(): string;

export function renderCloudflareHeaders(frameSrc?: string): string;
