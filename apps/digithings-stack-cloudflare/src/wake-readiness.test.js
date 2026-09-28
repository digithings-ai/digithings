import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins the container-wake readiness ports of DigiStackContainer.fetch (#4546).
 *
 * Every authenticated route verifies a digikey JWT, and the verifier fetches the
 * JWKS from the same container's digikey (:8005). The shared stack container
 * sleeps after 3 minutes idle (sleepAfter = "3m"), and digikey is the slowest
 * service to bind (container/start_digikey.sh waits up to 30s for redis). While
 * fetch() waited only for the requested service's port, a cold wake proxied
 * search.digithings.ai to digisearch before :8005 was listening, so the JWKS
 * fetch failed and the caller got 401 invalid_token (or 503
 * auth_backend_unavailable once the blocklist redis check ran). The digiquant
 * web-grounding pre-pass treats that as fatal (#3859), so a transient cold wake
 * discarded whole attempts.
 *
 * DIGIKEY_PORT is therefore unconditional. In practice this also covers the
 * blocklist 503 window: digikey waits up to 30s for redis before binding
 * (container/start_digikey.sh) and redis is a supervisord priority-10 program,
 * so redis is up first.
 *
 * Deliberately plain `.js`, same reason as container-bind.test.js: tsconfig
 * scopes `types` to @cloudflare/workers-types only.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackFetchSource() {
  const source = readFileSync(join(here, "index.ts"), "utf-8");
  const start = source.indexOf("override async fetch(");
  expect(start).toBeGreaterThan(-1);
  const end = source.indexOf("this.containerFetch(", start);
  expect(end).toBeGreaterThan(start);
  return source.slice(start, end);
}

describe("DigiStackContainer wake readiness", () => {
  it("waits for digikey on every request (JWKS issuer)", () => {
    const fetchSource = stackFetchSource();
    expect(fetchSource).toContain("ports:");
    expect(fetchSource).toContain("DIGIKEY_PORT,");
    expect(fetchSource).not.toContain("targetPort === DIGIKEY_PORT");
  });

  it("still waits for digigraph unconditionally", () => {
    expect(stackFetchSource()).toContain("DIGIGRAPH_PORT,");
  });

  it("waits for digisearch only on its own route", () => {
    expect(stackFetchSource()).toContain(
      "...(targetPort === DIGISEARCH_PORT ? [DIGISEARCH_PORT] : [])",
    );
  });
});
