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
