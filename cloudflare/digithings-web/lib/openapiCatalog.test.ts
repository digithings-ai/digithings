import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { OPENAPI_SERVICE_IDS, openApiSpecPath } from "./openapiCatalog";

const repoOpenapi = resolve(__dirname, "../../../docs/openapi");
const publicOpenapi = resolve(__dirname, "../public/openapi");
const webRoot = resolve(__dirname, "..");

function ensureSynced(): void {
  execFileSync(process.execPath, [resolve(webRoot, "lib/sync-openapi.mjs")], {
    cwd: webRoot,
    stdio: "pipe",
  });
}

describe("openapi catalog", () => {
  it("lists every committed OpenAPI JSON (except README)", () => {
    const onDisk = readdirSync(repoOpenapi)
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.replace(/\.json$/, ""))
      .sort();
    expect([...OPENAPI_SERVICE_IDS].sort()).toEqual(onDisk);
  });

  it("maps each service to a same-origin /openapi path", () => {
    for (const id of OPENAPI_SERVICE_IDS) {
      expect(openApiSpecPath(id)).toBe(`/openapi/${id}.json`);
    }
  });
});

describe("sync-openapi (prebuild artifact)", () => {
  it("sanitizes private servers out of public digichat copy when present", () => {
    if (!existsSync(resolve(publicOpenapi, "digichat.json"))) {
      ensureSynced();
    }
    const committed = JSON.parse(
      readFileSync(resolve(repoOpenapi, "digichat.json"), "utf8"),
    ) as { servers?: { url: string }[] };
    const published = JSON.parse(
      readFileSync(resolve(publicOpenapi, "digichat.json"), "utf8"),
    ) as { servers?: { url: string }[] };

    expect(
      (committed.servers ?? []).some((s) => s.url.includes("127.0.0.1")),
    ).toBe(true);
    expect(published.servers ?? []).toEqual([]);
  });

  it("vendors swagger-ui bundle + css into public/swagger-ui", () => {
    const swaggerDir = resolve(__dirname, "../public/swagger-ui");
    if (!existsSync(resolve(swaggerDir, "swagger-ui-bundle.js"))) {
      ensureSynced();
    }
    expect(existsSync(resolve(swaggerDir, "swagger-ui.css"))).toBe(true);
    expect(existsSync(resolve(swaggerDir, "swagger-ui-bundle.js"))).toBe(true);
    expect(
      existsSync(resolve(swaggerDir, "swagger-ui-standalone-preset.js")),
    ).toBe(true);
  });
});
