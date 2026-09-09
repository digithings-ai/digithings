import { describe, expect, it } from "vitest";
import {
  isAllowedMcpServerUrl,
  mcpServersHeaderValue,
  mergeMcpSessionOverlay,
  operatorMcpServersForUpstream,
  resolveMcpOAuthResourceUrl,
} from "./mcp-servers";
import type { DigichatDeployment } from "./schema";

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
});
