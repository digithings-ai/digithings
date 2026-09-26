import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEVKIT_SENTINEL,
  listDevkitEntries,
  redactSecretLines,
  stripDeploymentSecrets,
  type DigichatDeployment,
} from "./devkit-configs";

const VALID_SINGLE = `version: 1
deployment:
  slug: local-dev
  backend:
    type: digigraph
  token: super-secret-token
  gate:
    mode: ungated
    consumeUrl: https://quota.example.com/consume
  mcp:
    servers:
      - id: digisearch
        url: http://digisearch-mcp:8765/mcp
        token: mcp-secret
        tokenEnv: DIGISEARCH_TOKEN
`;

const INVALID_UNKNOWN_KEY = `version: 1
deployment:
  slug: bad
  backend:
    type: digigraph
  bogusKey: true
`;

const MULTI_HOST = `version: 1
hosts:
  example.com:
    slug: example
    backend:
      type: digigraph
    token: host-secret
`;

function makeConfigDir(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "devkit-"));
  for (const [rel, contents] of Object.entries(files)) {
    const abs = join(dir, rel);
    mkdirSync(join(abs, ".."), { recursive: true });
    writeFileSync(abs, contents);
  }
  return dir;
}

describe("redactSecretLines", () => {
  it("masks token and consumeUrl scalars, keeps the rest byte-identical", () => {
    const out = redactSecretLines(VALID_SINGLE);
    expect(out).toContain(`token: ${DEVKIT_SENTINEL}`);
    expect(out).toContain(`consumeUrl: ${DEVKIT_SENTINEL}`);
    expect(out).not.toContain("super-secret-token");
    expect(out).not.toContain("mcp-secret");
    expect(out).not.toContain("https://quota.example.com/consume");
    // Non-secret lines untouched.
    expect(out).toContain("tokenEnv: DIGISEARCH_TOKEN");
    expect(out).toContain("slug: local-dev");
  });

  it("masks quoted secret keys", () => {
    const text = `version: 1
deployment:
  slug: q
  backend:
    type: digigraph
  "token": quoted-secret-value
  gate:
    mode: ungated
    'consumeUrl': 'https://quota.example.com/q'
  # token: not-a-real-line
`;
    const out = redactSecretLines(text);
    expect(out).not.toContain("quoted-secret-value");
    expect(out).not.toContain("https://quota.example.com/q");
    expect(out).toContain(`"token": ${DEVKIT_SENTINEL}`);
    expect(out).toContain(`'consumeUrl': ${DEVKIT_SENTINEL}`);
    expect(out).toContain("# token: not-a-real-line");
  });

  it("masks block-scalar continuations until indentation returns", () => {
    const text = `version: 1
deployment:
  slug: b
  backend:
    type: digigraph
  token: |
    block-secret-line-one
    block-secret-line-two
  gate:
    mode: ungated
  mcp:
    servers:
      - id: s
        url: http://x/mcp
        token: >-
          folded-mcp-secret
  after: true
`;
    const out = redactSecretLines(text);
    expect(out).not.toContain("block-secret-line-one");
    expect(out).not.toContain("block-secret-line-two");
    expect(out).not.toContain("folded-mcp-secret");
    expect(out).toContain(`token: ${DEVKIT_SENTINEL}`);
    // Structure around the block is preserved.
    expect(out).toContain("gate:");
    expect(out).toContain("after: true");
  });
});

describe("stripDeploymentSecrets", () => {
  it("removes token, consumeUrl, and mcp server tokens", () => {
    const dep = {
      slug: "x",
      token: "t",
      gate: { mode: "ungated", consumeUrl: "https://q.example/c" },
      mcp: {
        servers: [
          {
            id: "s",
            url: "http://x/mcp",
            token: "m",
            setup: { index_name: "secret-index" },
          },
        ],
        allowUserServers: false,
        allowAddForm: false,
      },
    } as unknown as DigichatDeployment;
    const stripped = stripDeploymentSecrets(dep);
    expect(JSON.stringify(stripped)).not.toContain("super-secret-token");
    expect(JSON.stringify(stripped)).not.toContain("secret-index");
    expect(stripped.token).toBeUndefined();
    expect(stripped.gate.consumeUrl).toBeUndefined();
    expect(stripped.mcp?.servers[0].token).toBeUndefined();
    expect(stripped.mcp?.servers[0].setup).toBeUndefined();
    // Original untouched.
    expect(dep.token).toBe("t");
  });
});

describe("listDevkitEntries", () => {
  it("lists valid files with redacted text and stripped deployments", () => {
    const dir = makeConfigDir({ "local.yaml": VALID_SINGLE });
    const entries = listDevkitEntries(dir, {}, dir);
    expect(entries).toHaveLength(1);
    const [entry] = entries;
    expect(entry.ok).toBe(true);
    expect(entry.label).toBe("local-dev");
    expect(entry.readOnly).toBe(false);
    const payload = JSON.stringify(entry);
    expect(payload).not.toContain("super-secret-token");
    expect(payload).not.toContain("mcp-secret");
    expect(payload).not.toContain("https://quota.example.com/consume");
    expect(entry.redactedText).toContain(DEVKIT_SENTINEL);
    expect(entry.deployment?.slug).toBe("local-dev");
  });

  it("surfaces strict-schema violations as issues with null deployment", () => {
    const dir = makeConfigDir({ "bad.yaml": INVALID_UNKNOWN_KEY });
    const entries = listDevkitEntries(dir, {}, dir);
    expect(entries).toHaveLength(1);
    expect(entries[0].ok).toBe(false);
    expect(entries[0].deployment).toBeNull();
    expect(entries[0].issues.length).toBeGreaterThan(0);
    expect(entries[0].issues.join(";")).toContain("bogusKey");
  });

  it("surfaces invalid YAML as issues", () => {
    const dir = makeConfigDir({ "broken.yaml": "deployment:\n\t- unbalanced: [oops" });
    const entries = listDevkitEntries(dir, {}, dir);
    expect(entries[0].ok).toBe(false);
    expect(entries[0].issues.join(";")).toContain("invalid YAML");
  });

  it("expands hosts registries into one entry per host", () => {
    const dir = makeConfigDir({ "multi.yaml": MULTI_HOST });
    const entries = listDevkitEntries(dir, {}, dir);
    expect(entries).toHaveLength(1);
    expect(entries[0].id).toBe("file:multi.yaml#hosts/example.com");
    expect(entries[0].label).toBe("example");
    expect(JSON.stringify(entries[0])).not.toContain("host-secret");
  });

  it("lists embed-tenant env hosts as read-only entries with stripped secrets", () => {
    const dir = makeConfigDir({});
    const tenants = JSON.stringify({
      "env.example.com": {
        slug: "env-host",
        backend: { type: "digigraph" },
        gateMode: "ungated",
        token: "env-token-secret",
      },
    });
    const entries = listDevkitEntries(dir, { DIGICHAT_EMBED_TENANTS: tenants }, dir);
    const envEntries = entries.filter((e) => e.kind === "env");
    expect(envEntries).toHaveLength(1);
    expect(envEntries[0].readOnly).toBe(true);
    expect(envEntries[0].redactedText).toBeNull();
    expect(JSON.stringify(envEntries[0])).not.toContain("env-token-secret");
  });
});
