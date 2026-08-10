/** Hand-written declarations for security-headers.mjs. */

export const DEFAULT_DIGICHAT_EMBED_ORIGIN: string;

export function resolveDigichatEmbedOrigin(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string | null;

export function frameSrcForCsp(
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>,
): string;

export function digithingsCsp(frameSrc?: string): string;

export function renderCloudflareHeaders(frameSrc?: string): string;
