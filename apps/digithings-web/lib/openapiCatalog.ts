/**
 * Public OpenAPI explorer catalog — one entry per committed spec under
 * docs/openapi/*.json (synced into public/openapi/ at digithings-web prebuild).
 * digibot has no HTTP OpenAPI and is intentionally omitted.
 */

import {
  OPENAPI_SERVICES,
  type OpenApiService,
} from "@digithings/catalog/openapi";

export type { OpenApiService };
export { OPENAPI_SERVICES };
export { OPENAPI_SERVICE_IDS } from "@digithings/catalog/openapi";

export function openApiSpecPath(id: string): string {
  return `/openapi/${id}.json`;
}
