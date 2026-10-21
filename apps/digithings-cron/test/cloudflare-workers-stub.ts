/**
 * Vitest stand-in for `cloudflare:workers`. Production uses the real module.
 *
 * The real `DurableObject` is what makes a Durable Object class RPC-capable:
 * a class that does not extend it has no callable methods on its stub, and the
 * runtime refuses the call with "The receiving Durable Object does not support
 * RPC, because its class was not declared with `extends DurableObject`".
 * The stub keeps the same shape - `ctx` and `env` on the instance - so the
 * unit tests exercise the same field access the deployed class does.
 */
export class DurableObject<T = unknown> {
  protected ctx: DurableObjectState;
  protected env: T;
  constructor(ctx: DurableObjectState, env: T) {
    this.ctx = ctx;
    this.env = env;
  }
}

export class WorkerEntrypoint {}
