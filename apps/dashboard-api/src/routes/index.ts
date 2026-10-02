/**
 * Domain route modules. `index.ts` consults the registry for any path the
 * legacy table does not serve. The eight shipped routes stay in their builders.
 */

import { identityTrusted } from "../access";
import type { Env } from "../index";
import { registerFx } from "./fx";
import { registerPipeline } from "./pipeline";
import { registerPortfolio } from "./portfolio";
import { Registry, type RouteModule } from "./registry";

export const ROUTE_MODULES: RouteModule<Env>[] = [registerPortfolio, registerPipeline, registerFx];

export function buildRegistry(modules: readonly RouteModule<Env>[] = ROUTE_MODULES): Registry<Env> {
  const reg = new Registry<Env>();
  for (const m of modules) m(reg);
  return reg;
}

/** Verified user id from the edge-injected `x-digi-user`; null when absent or malformed (fail closed). */
export function userIdFor(request: Request, env: { DASHBOARD_EDGE_KEY?: string } = {}): string | null {
  if (!identityTrusted(request, env)) return null;
  const v = (request.headers.get("x-digi-user") ?? "").trim();
  return v.length > 0 && v.length <= 128 && /^[\w@.:+-]+$/.test(v) ? v : null;
}
