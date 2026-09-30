import { describe, expect, it } from "vitest";
import { buildComposeBundle, buildEmbedBundle, detectExportSecrets } from "./devkit-export";

const SERVER_TEXT = [
  "version: 1",
  "deployment:",
  "  slug: demo",
  "  token: live-deploy-token",
  "  backend:",
  "    type: digigraph",
  "  mcp:",
  "    servers:",
  "      - id: zammad",
  "        url: http://zammad-mcp:8770/mcp",
  "        tokenEnv: ZAMMAD_API_TOKEN",
  "        token: server-secret",
  "      - id: plain",
  "        url: http://plain:1/mcp",
  "        token: other-secret",
  "  gate:",
  "    mode: ungated",
  "    activityDetail: labels",
  "    consumeUrl: https://quota.example.com/consume",
].join("\n");

describe("detectExportSecrets", () => {
  it("maps deployment token, server tokens, and consumeUrl to vars", () => {
    const secrets = detectExportSecrets(SERVER_TEXT);
    expect(secrets.map((s) => [s.key, s.variable])).toEqual([
      ["token", "DIGICHAT_EMBED_TOKEN"],
      ["token", "ZAMMAD_API_TOKEN"],
      ["token", "PLAIN_TOKEN"],
      ["consumeUrl", "DIGICHAT_CONSUME_URL"],
    ]);
  });

  it("finds nothing in a secret-free draft", () => {
    expect(detectExportSecrets("version: 1\ndeployment:\n  slug: x\n  backend:\n    type: digigraph\n")).toEqual([]);
  });
});

describe("buildComposeBundle", () => {
  it("substitutes placeholders and keeps every other byte", () => {
    const bundle = buildComposeBundle("demo", SERVER_TEXT);
    expect(bundle.hasSentinel).toBe(false);
    expect(bundle.configYaml).toContain("token: ${DIGICHAT_EMBED_TOKEN}");
    expect(bundle.configYaml).toContain("token: ${ZAMMAD_API_TOKEN}");
    expect(bundle.configYaml).toContain("token: ${PLAIN_TOKEN}");
    expect(bundle.configYaml).toContain("consumeUrl: ${DIGICHAT_CONSUME_URL}");
    expect(bundle.configYaml).not.toContain("live-deploy-token");
    expect(bundle.configYaml).toContain("  backend:\n    type: digigraph");
    expect(bundle.envFragment).toContain("DIGICHAT_CONFIG_PATH=/app/config/demo.yaml");
    expect(bundle.envFragment).toContain("AUTH_SECRET=");
    expect(bundle.upCommand).toContain("--profile digichat");
    expect(bundle.checklist.join("\n")).toContain("ZAMMAD_API_TOKEN");
  });

  it("collapses block-scalar secrets to a single placeholder line", () => {
    const text = "deployment:\n  slug: x\n  token: |\n    line-one\n    line-two\n  backend:\n    type: digigraph\n";
    const bundle = buildComposeBundle("x", text);
    expect(bundle.configYaml).toContain("token: ${DIGICHAT_EMBED_TOKEN}");
    expect(bundle.configYaml).not.toContain("line-one");
    expect(bundle.configYaml).toContain("backend:");
  });

  it("flags sentinel drafts so copy-YAML can stay blocked", () => {
    const text = SERVER_TEXT.replace("live-deploy-token", "__DEVKIT_PRESERVED__");
    const bundle = buildComposeBundle("demo", text);
    expect(bundle.hasSentinel).toBe(true);
    expect(bundle.configYaml).toContain("${DIGICHAT_EMBED_TOKEN}");
  });
});

describe("buildEmbedBundle", () => {
  it("uses the hosts key when present, placeholders otherwise", () => {
    const withHost = buildEmbedBundle("occ", "occ.digithings.ai");
    expect(withHost.snippet).toContain("host=occ.digithings.ai");
    expect(withHost.envLines).toContain("DIGICHAT_EMBED_HOSTS=occ.digithings.ai");
    const plain = buildEmbedBundle("demo", null);
    expect(plain.snippet).toContain("host=<parent-host>");
  });
});
