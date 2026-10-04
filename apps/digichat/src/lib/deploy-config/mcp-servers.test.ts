import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import {
  isAllowedMcpServerUrl,
  mcpServersHeaderValue,
  mcpUpstreamHeaderValue,
  mergeMcpSessionOverlay,
  operatorMcpServersForUpstream,
  resolveMcpOAuthResourceUrl,
} from "./mcp-servers";
import type { DigichatDeployment } from "./schema";
import { parseDigichatConfig } from "./schema";

const examplesDir = resolve(__dirname, "../../../config/examples");

describe("isAllowedMcpServerUrl", () => {
  it("accepts public https and docker http", () => {
    expect(isAllowedMcpServerUrl("https://mcp.datatap.example/mcp")).toBe(true);
    expect(isAllowedMcpServerUrl("http://datatap-mcp:8080/mcp")).toBe(true);
  });

  it("rejects credentials, metadata, loopback, and rebinding hosts", () => {
    expect(isAllowedMcpServerUrl("https://user:pass@evil.test/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("https://169.254.169.254/latest")).toBe(false);
    expect(isAllowedMcpServerUrl("ftp://mcp.example/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("http://127.0.0.1:8005/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://localhost:8080/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("http://[::1]/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("http://2130706433/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://[::ffff:169.254.169.254]/latest/meta-data/")).toBe(
      false,
    );
    expect(isAllowedMcpServerUrl("http://169.254.169.254.nip.io/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://10.0.0.5:8080/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("http://[fd12:3456::1]/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("http://0x7f000001/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://127.1/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://0x7f.0x0.0x0.0x1/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://localtest.me/")).toBe(false);
    expect(isAllowedMcpServerUrl("http://foo.lvh.me/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("http://100.100.100.200/")).toBe(false);
  });
});

describe("operatorMcpServersForUpstream", () => {
  it("forwards operator YAML servers and drops bad urls", () => {
    const dep = {
      slug: "datatap",
      mcp: {
        servers: [
          { id: "datatap", url: "https://mcp.datatap.example/mcp", label: "DataTap" },
          { id: "bad", url: "https://169.254.169.254/" },
        ],
      },
    } as DigichatDeployment;
    expect(operatorMcpServersForUpstream(dep)).toEqual([
      { id: "datatap", url: "https://mcp.datatap.example/mcp" },
    ]);
    expect(mcpServersHeaderValue(dep)).toContain("datatap");
  });

  it("carries operator token/authHeader (#3841) into the upstream header", () => {
    const dep = {
      slug: "datatap",
      mcp: {
        servers: [
          {
            id: "datatap",
            url: "https://mcp.datatap.example/mcp",
            token: "tenant-static-key",
            authHeader: "X-API-Key",
          },
        ],
      },
    } as DigichatDeployment;
    const forwarded = operatorMcpServersForUpstream(dep);
    expect(forwarded).toEqual([
      {
        id: "datatap",
        url: "https://mcp.datatap.example/mcp",
        token: "tenant-static-key",
        authHeader: "X-API-Key",
      },
    ]);
    const header = mcpUpstreamHeaderValue(forwarded);
    expect(header).toBeDefined();
    expect(JSON.parse(header ?? "[]")).toEqual([
      {
        id: "datatap",
        url: "https://mcp.datatap.example/mcp",
        token: "tenant-static-key",
        authHeader: "X-API-Key",
      },
    ]);
  });

  it("omits authHeader when no operator token is set", () => {
    const dep = {
      slug: "datatap",
      mcp: {
        servers: [{ id: "datatap", url: "https://mcp.datatap.example/mcp", authHeader: "X-API-Key" }],
      },
    } as DigichatDeployment;
    expect(operatorMcpServersForUpstream(dep)).toEqual([
      { id: "datatap", url: "https://mcp.datatap.example/mcp" },
    ]);
  });
});

describe("mergeMcpSessionOverlay", () => {
  it("attaches overlay token to operator URL and ignores overlay URL steal", () => {
    const merged = mergeMcpSessionOverlay({
      operator: [{ id: "datatap", url: "https://mcp.datatap.example/mcp" }],
      overlay: [
        {
          id: "datatap",
          url: "https://evil.example/mcp",
          auth: "oauth",
          token: "tok",
        },
      ],
      allowSessionUrls: true,
    });
    expect(merged).toEqual([
      {
        id: "datatap",
        url: "https://mcp.datatap.example/mcp",
        auth: "oauth",
        token: "tok",
      },
    ]);
  });

  it("adds allowlisted session URLs only when allowSessionUrls is on", () => {
    const overlay = [{ id: "linear", url: "https://mcp.linear.app/mcp", auth: "oauth" }];
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay,
        allowSessionUrls: false,
      }),
    ).toEqual([]);
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay,
        allowSessionUrls: true,
      }),
    ).toEqual([{ id: "linear", url: "https://mcp.linear.app/mcp", auth: "oauth" }]);
  });

  it("rejects loopback session URLs", () => {
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay: [{ id: "local", url: "http://127.0.0.1:8080/mcp" }],
        allowSessionUrls: true,
      }),
    ).toEqual([]);
  });

  it("keeps operator authHeader even when a session overlay overrides the token (#3841)", () => {
    const merged = mergeMcpSessionOverlay({
      operator: [
        {
          id: "datatap",
          url: "https://mcp.datatap.example/mcp",
          token: "operator-static-key",
          authHeader: "X-API-Key",
        },
      ],
      overlay: [{ id: "datatap", auth: "bearer", token: "visitor-oauth-token" }],
      allowSessionUrls: false,
    });
    expect(merged).toEqual([
      {
        id: "datatap",
        url: "https://mcp.datatap.example/mcp",
        token: "visitor-oauth-token",
        authHeader: "X-API-Key",
        auth: "bearer",
      },
    ]);
  });

  it("session overlay items can never carry an authHeader field through to upstream", () => {
    // McpSessionOverlayItem has no authHeader field at the type level; this
    // asserts the runtime behavior matches — an overlay-only id (no operator
    // entry) never gets an authHeader even if injected via a loose object.
    const merged = mergeMcpSessionOverlay({
      operator: [],
      overlay: [
        { id: "evil", url: "https://mcp.evil.example/mcp", authHeader: "X-Injected" } as {
          id: string;
          url?: string;
        },
      ],
      allowSessionUrls: true,
    });
    expect(merged).toEqual([{ id: "evil", url: "https://mcp.evil.example/mcp" }]);
  });

  it("a session overlay item can never carry allowedTools or mutatingTools through to upstream", () => {
    // McpSessionOverlayItem has no allowedTools/mutatingTools fields at the type
    // level; this asserts the runtime behavior matches — an overlay-only id
    // (no operator entry) never gets a tool allowlist even if injected via a
    // loose object. Deny-by-default: a session connector starts with zero
    // tools and can only ever narrow, never widen, the operator allowlist.
    const merged = mergeMcpSessionOverlay({
      operator: [],
      overlay: [
        {
          id: "evil",
          url: "https://mcp.evil.example/mcp",
          allowedTools: ["*"],
          mutatingTools: ["deleteEverything"],
        } as { id: string; url?: string },
      ],
      allowSessionUrls: true,
    });
    expect(merged).toEqual([{ id: "evil", url: "https://mcp.evil.example/mcp" }]);
    expect(merged[0]).not.toHaveProperty("allowedTools");
    expect(merged[0]).not.toHaveProperty("mutatingTools");
  });

  it("a session overlay entry cannot override the operator allowlist", () => {
    // Operator-only by construction: the overlay is merged onto an existing
    // operator row, and mergeMcpSessionOverlay only ever writes `auth` and
    // `token` onto it. The operator allowlist survives untouched, and the
    // overlay cannot introduce a `mutatingTools` the operator did not declare.
    const merged = mergeMcpSessionOverlay({
      operator: [
        {
          id: "atlassian",
          url: "https://mcp.atlassian.com/v1/sse",
          allowedTools: ["addOrEditJiraIssueComment"],
        },
      ],
      overlay: [
        {
          id: "atlassian",
          auth: "oauth",
          token: "visitor-oauth-token",
          allowedTools: ["executeWrite"],
          mutatingTools: ["executeWrite"],
        } as { id: string; auth?: string; token?: string },
      ],
      allowSessionUrls: false,
    });
    expect(merged).toEqual([
      {
        id: "atlassian",
        url: "https://mcp.atlassian.com/v1/sse",
        allowedTools: ["addOrEditJiraIssueComment"],
        auth: "oauth",
        token: "visitor-oauth-token",
      },
    ]);
    expect(merged[0]).not.toHaveProperty("mutatingTools");
  });

  it("rejects http session URLs even when host would otherwise pass SSRF (#3795)", () => {
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay: [{ id: "insecure", url: "http://mcp.datatap.example/mcp" }],
        allowSessionUrls: true,
      }),
    ).toEqual([]);
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay: [{ id: "secure", url: "https://mcp.datatap.example/mcp" }],
        allowSessionUrls: true,
      }),
    ).toEqual([{ id: "secure", url: "https://mcp.datatap.example/mcp" }]);
  });

  it("accepts a mixed-case HTTPS scheme but still rejects mixed-case HTTP", () => {
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay: [{ id: "linear", url: "HTTPS://mcp.linear.app/mcp" }],
        allowSessionUrls: true,
      }),
    ).toEqual([{ id: "linear", url: "HTTPS://mcp.linear.app/mcp" }]);
    expect(
      mergeMcpSessionOverlay({
        operator: [],
        overlay: [{ id: "insecure", url: "HTTP://mcp.datatap.example/mcp" }],
        allowSessionUrls: true,
      }),
    ).toEqual([]);
  });
});

describe("mcpServersHeaderValue operator tool allowlist (DIG-284)", () => {
  it("forwards allowedTools and mutatingTools to the upstream header", () => {
    // The digigraph side reads these exact spellings off the X-Digi-Mcp-Servers
    // JSON rows, so the key names are the wire contract — pin them literally.
    const dep = {
      slug: "acme",
      mcp: {
        servers: [
          {
            id: "atlassian",
            url: "https://mcp.atlassian.com/v1/sse",
            label: "Atlassian",
            allowedTools: ["addOrEditJiraIssueComment"],
            mutatingTools: ["addOrEditJiraIssueComment"],
          },
        ],
      },
    } as unknown as DigichatDeployment;
    const header = mcpServersHeaderValue(dep);
    expect(header).toBeDefined();
    const rows = JSON.parse(header ?? "[]") as Record<string, unknown>[];
    expect(rows).toHaveLength(1);
    expect(Object.keys(rows[0] ?? {})).toEqual(
      expect.arrayContaining(["id", "url", "allowedTools", "mutatingTools"]),
    );
    expect(rows[0]?.allowedTools).toEqual(["addOrEditJiraIssueComment"]);
    expect(rows[0]?.mutatingTools).toEqual(["addOrEditJiraIssueComment"]);
    // Never client-projected: only id/url and the two allowlists reach the row.
    expect(rows[0]?.label).toBeUndefined();
  });

  it("omits both keys entirely when the operator sets neither", () => {
    // Do not forward `allowedTools: []`. An empty array and an absent key mean
    // the same thing to digigraph (zero tools), but shipping the key would add
    // bytes to every row and invite a reader to think [] widens the allowlist.
    const dep = {
      slug: "acme",
      mcp: {
        servers: [
          {
            id: "datatap",
            url: "https://mcp.datatap.example/mcp",
            label: "DataTap",
          },
        ],
      },
    } as unknown as DigichatDeployment;
    const header = mcpServersHeaderValue(dep);
    expect(header).toBeDefined();
    const rows = JSON.parse(header ?? "[]") as Record<string, unknown>[];
    expect(rows).toEqual([{ id: "datatap", url: "https://mcp.datatap.example/mcp" }]);
    expect(rows[0]).not.toHaveProperty("allowedTools");
    expect(rows[0]).not.toHaveProperty("mutatingTools");
  });

  it("omits an over-budget allowlist whole rather than truncating it", () => {
    // The projection half of the same bound (review #5061 round 2, S1). The dep
    // literal bypasses zod on purpose, because zod is the check that runs first
    // in production: the loader parses, then we project, so this layer only ever
    // sees an over-budget list if the two bounds have drifted apart — which is
    // exactly what the shared-constant import exists to prevent, and exactly what
    // this assertion catches if it ever happens. Truncating here instead of
    // dropping would produce an allowlist that lost tools the operator named and
    // still looked configured, so the whole list goes.
    const overBudget = Array.from({ length: 257 }, (_, i) => `digifetch_read_${i}`);
    const dep = {
      slug: "acme",
      mcp: {
        servers: [
          {
            id: "digiquant",
            url: "https://mcp.digithings.ai/mcp",
            allowedTools: overBudget,
            mutatingTools: overBudget,
          },
        ],
      },
    } as unknown as DigichatDeployment;
    const header = mcpServersHeaderValue(dep);
    expect(header).toBeDefined();
    const rows = JSON.parse(header ?? "[]") as Record<string, unknown>[];
    // The row itself still ships — only the unforwardable lists are gone.
    expect(rows).toEqual([{ id: "digiquant", url: "https://mcp.digithings.ai/mcp" }]);
  });

  it("omits an allowlist carrying one over-long name, whole", () => {
    // The other branch of `boundedToolAllowlist`, and the name-bound counterpart
    // of the test above. A single 65th character disqualifies the whole list: it
    // is a name digigraph truncates, and a truncated name can collide with a
    // different tool, which is precisely the ambiguity the bound exists to
    // prevent. Dropping only the offending entry would grant the rest of a list
    // that was wrong about something.
    const dep = {
      slug: "acme",
      mcp: {
        servers: [
          {
            id: "atlassian",
            url: "https://mcp.atlassian.com/v1/sse",
            allowedTools: ["search_tickets", "t".repeat(65)],
          },
        ],
      },
    } as unknown as DigichatDeployment;
    const header = mcpServersHeaderValue(dep);
    expect(header).toBeDefined();
    const rows = JSON.parse(header ?? "[]") as Record<string, unknown>[];
    expect(rows).toEqual([{ id: "atlassian", url: "https://mcp.atlassian.com/v1/sse" }]);
  });
});

describe("every shipped operator row names its tools (DIG-284 deny-by-default)", () => {
  // Once leaf 284.1 lands, a row with no `allowedTools` offers *zero* tools. So
  // each shipped row has to name its catalog, and the count is the cheapest way
  // to notice when a hand-edit drops or invents a name. The numbers come from
  // the source of each server, not from the YAML:
  //   digiquant  — READ_SCOPE_TOOLS, digiquant/src/digiquant/mcp_server.py
  //   zammad     — @mcp.tool() in scripts/zammad_mcp/server.py
  //   digisearch — @mcp.tool() in digisearch/src/digisearch/mcp_server.py
  //   digivault  — DISPATCH_TOOL_NAMES, digivault/src/digivault/tool_dispatch.py
  const rows = [
    { file: "dashboard-modal.yaml", id: "digiquant", count: 113 },
    { file: "occ-embed.yaml", id: "zammad", count: 5 },
    { file: "occ-embed.yaml", id: "digisearch", count: 16 },
    { file: "occ-embed.yaml", id: "digivault", count: 6 },
    { file: "digithings-ai-embed.yaml", id: "digisearch", count: 16 },
    { file: "digithings-ai-embed.yaml", id: "digivault", count: 6 },
  ];
  // Rows live under `deployment.mcp` in some files and under a host's `mcp` in
  // others (`occ-embed.yaml` and `digithings-ai-embed.yaml` are `hosts:` files),
  // so collect from wherever the row actually is rather than guessing the shape.
  const allServerRows = (cfg: ReturnType<typeof parseDigichatConfig>) => {
    const out: { id: string; allowedTools?: string[] }[] = [];
    const scopes = [cfg.deployment, ...Object.values(cfg.hosts ?? {})];
    for (const scope of scopes) {
      for (const s of (scope as { mcp?: { servers?: typeof out } })?.mcp?.servers ?? []) {
        out.push(s);
      }
    }
    return out;
  };
  it.each(rows)("$file [$id] names exactly $count tools", ({ file, id, count }) => {
    const cfg = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, file), "utf8")),
      file,
    );
    const row = allServerRows(cfg).find((s) => s.id === id);
    expect(row, `${file} has no mcp.servers row with id ${id}`).toBeDefined();
    expect(row?.allowedTools).toHaveLength(count);
    expect(row?.allowedTools).toEqual([...(row?.allowedTools ?? [])].sort());
    expect(new Set(row?.allowedTools).size).toBe(count);
  });

  it("leaves the two DataTap rows unenumerated, on purpose and visibly", () => {
    // DataTap's catalog is only knowable from a remote `tools/list`, so these two
    // rows cannot be enumerated ahead of connect. Under deny-by-default they
    // therefore go dark when 284.1 lands — which is the point of this test: it
    // fails the moment someone enumerates them, so the decision gets made rather
    // than inherited. The open question (read `tools/list`, or narrow the server)
    // is on DIG-409; do not resolve it by editing a number here.
    for (const file of ["datatap-mcp.yaml", "../datatap-trial-test.yaml"]) {
      const cfg = parseDigichatConfig(
        loadYaml(readFileSync(resolve(examplesDir, file), "utf8")),
        file,
      );
      const rows = allServerRows(cfg);
      expect(rows.map((s) => s.id)).toEqual(["datatap"]);
      expect(rows[0]?.allowedTools).toBeUndefined();
      expect((rows[0] as { mutatingTools?: string[] } | undefined)?.mutatingTools).toBeUndefined();
    }
  });
});

describe("dashboard-modal operator digiquant server", () => {
  it("declares exactly the digiquant read-scope server", () => {
    const cfg = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, "dashboard-modal.yaml"), "utf8")),
      "dashboard-modal.yaml",
    );
    const dep = cfg.deployment;
    expect(dep?.mcp?.allowUserServers).toBe(false);
    expect(dep?.mcp?.allowAddForm).toBe(false);
    expect(dep?.mcp?.servers).toHaveLength(1);
    const row = dep?.mcp?.servers?.[0];
    // Exactly these keys — the previous `toEqual` on the whole row was what
    // caught the allowlist landing here, and pinning the key set keeps that
    // signal without pasting 113 names into the fixture.
    expect(Object.keys(row ?? {}).sort()).toEqual([
      "allowedTools",
      "default",
      "id",
      "label",
      "url",
    ]);
    expect(row).toMatchObject({
      id: "digiquant",
      url: "https://mcp.digithings.ai/mcp",
      label: "digiquant market data",
      default: true,
    });
    // DIG-284 deny-by-default: the row names its whole read scope, and it names
    // it exactly — `READ_SCOPE_TOOLS` in `digiquant/src/digiquant/mcp_server.py`
    // has 113 entries and this one keeps its longest. Sorted, so a hand-edit
    // that drops or duplicates a name is visible in a diff.
    expect(row?.allowedTools).toHaveLength(113);
    expect(row?.allowedTools).toContain("dashboard_get_policy_gate_evaluation");
    expect(row?.allowedTools).toEqual([...(row?.allowedTools ?? [])].sort());
    expect(new Set(row?.allowedTools).size).toBe(113);
    // Nothing is flagged as mutating: `READ_SCOPE_TOOLS` is the read surface by
    // construction, and digigraph owns the mutating decision anyway (DIG-284
    // decision D1) — `mutatingTools` is an operator hint, not the gate.
    expect(row?.mutatingTools).toBeUndefined();
  });

  it("a session overlay entry with the same id cannot override the operator URL", () => {
    const merged = mergeMcpSessionOverlay({
      operator: [{ id: "digiquant", url: "https://mcp.digithings.ai/mcp" }],
      overlay: [{ id: "digiquant", url: "https://evil.example/mcp" }],
      allowSessionUrls: true,
    });
    expect(merged).toEqual([{ id: "digiquant", url: "https://mcp.digithings.ai/mcp" }]);
  });
});

describe("resolveMcpOAuthResourceUrl", () => {
  const operator = [{ id: "datatap", url: "http://datatap-mcp:8080/mcp" }];

  it("uses the operator URL even when session servers are off", () => {
    expect(
      resolveMcpOAuthResourceUrl({
        operator,
        id: "datatap",
        clientUrl: "https://evil.example/mcp",
        allowUserServers: false,
      }),
    ).toBe("http://datatap-mcp:8080/mcp");
  });

  it("ignores client URLs unless allowUserServers is on", () => {
    expect(
      resolveMcpOAuthResourceUrl({
        operator: [],
        id: "linear",
        clientUrl: "https://mcp.linear.app/mcp",
        allowUserServers: false,
      }),
    ).toBe("");
    expect(
      resolveMcpOAuthResourceUrl({
        operator: [],
        id: "linear",
        clientUrl: "https://mcp.linear.app/mcp",
        allowUserServers: true,
      }),
    ).toBe("https://mcp.linear.app/mcp");
    expect(
      resolveMcpOAuthResourceUrl({
        operator: [],
        id: "linear",
        clientUrl: "http://localtest.me/mcp",
        allowUserServers: true,
      }),
    ).toBe("");
  });

  it("accepts a mixed-case HTTPS scheme but still rejects mixed-case HTTP", () => {
    expect(
      resolveMcpOAuthResourceUrl({
        operator: [],
        id: "linear",
        clientUrl: "HTTPS://mcp.linear.app/mcp",
        allowUserServers: true,
      }),
    ).toBe("HTTPS://mcp.linear.app/mcp");
    expect(
      resolveMcpOAuthResourceUrl({
        operator: [],
        id: "insecure",
        clientUrl: "HTTP://mcp.datatap.example/mcp",
        allowUserServers: true,
      }),
    ).toBe("");
  });
});
