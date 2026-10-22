/** Vitest stand-in for `cloudflare:workers`. Production uses the real module. */
export class DurableObject<T = unknown> {
  ctx: unknown;
  env: T;
  constructor(ctx: unknown, env: T) {
    this.ctx = ctx;
    this.env = env;
  }
}

export class WorkerEntrypoint {}

/**
 * The Worker bindings, read at module scope by index.ts.
 *
 * The unit suite has no bindings, so every lookup answers undefined and the
 * code under test falls back to its documented defaults.
 */
export const env: Record<string, unknown> = {};
