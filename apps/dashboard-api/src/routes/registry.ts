/**
 * Route registry: each domain (portfolio, pipeline, fx, ...) lives in
 * `src/routes/<domain>.ts` and registers its routes here. Paths may carry
 * `{name}` template segments (same syntax as the access catalog). Exact paths
 * win over templates. Writes (PUT/POST/DELETE) exist only when a module
 * registers them; the dispatcher in `index.ts` gates them (verified user +
 * catalog verdict) before a handler ever runs.
 */

import type { Caller } from "../access";

export type Method = "GET" | "PUT" | "POST" | "DELETE";

export interface RouteCtx<E> {
  env: E;
  /** `{name}` template segments, URI-decoded. */
  params: Record<string, string>;
  /** Verified `x-digi-user`; always set on writes, null on reads without one. */
  userId: string | null;
  caller: Caller;
}

export type RouteFn<E> = (req: Request, ctx: RouteCtx<E>) => Promise<Response>;

/** A domain module: registers its routes on the shared registry. */
export type RouteModule<E> = (reg: Registry<E>) => void;

/** Params for a template route that matches `path`, else null. */
export function matchPath(route: string, path: string): Record<string, string> | null {
  const a = route.split("/");
  const b = path.split("/");
  if (a.length !== b.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < a.length; i++) {
    const seg = a[i]!;
    if (seg.startsWith("{") && seg.endsWith("}")) {
      if (b[i] === "") return null;
      try {
        params[seg.slice(1, -1)] = decodeURIComponent(b[i]!);
      } catch {
        return null;
      }
    } else if (seg !== b[i]) return null;
  }
  return params;
}

interface Entry<E> {
  method: Method;
  path: string;
  fn: RouteFn<E>;
}

export class Registry<E> {
  private entries: Entry<E>[] = [];

  add(method: Method, path: string, fn: RouteFn<E>): void {
    if (this.entries.some((e) => e.method === method && e.path === path)) {
      throw new Error(`duplicate route ${method} ${path}`);
    }
    this.entries.push({ method, path, fn });
  }

  get(path: string, fn: RouteFn<E>): void {
    this.add("GET", path, fn);
  }

  match(method: string, path: string): { fn: RouteFn<E>; params: Record<string, string> } | null {
    const same = this.entries.filter((e) => e.method === method);
    const exact = same.find((e) => e.path === path);
    if (exact) return { fn: exact.fn, params: {} };
    for (const e of same) {
      const params = matchPath(e.path, path);
      if (params) return { fn: e.fn, params };
    }
    return null;
  }

  /** Registered routes, for the catalog-parity checks and MCP generation. */
  list(): ReadonlyArray<{ method: Method; path: string }> {
    return this.entries.map(({ method, path }) => ({ method, path }));
  }
}
