import { describe, expect, it } from "vitest";
import {
  isAllowedMcpServerUrl,
  mcpServersHeaderValue,
  operatorMcpServersForUpstream,
} from "./mcp-servers";
import type { DigichatDeployment } from "./schema";

describe("isAllowedMcpServerUrl", () => {
  it("accepts public https and docker http", () => {
    expect(isAllowedMcpServerUrl("https://mcp.datatap.example/mcp")).toBe(true);
    expect(isAllowedMcpServerUrl("http://datatap-mcp:8080/mcp")).toBe(true);
  });

  it("rejects credentials, metadata, and junk", () => {
    expect(isAllowedMcpServerUrl("https://user:pass@evil.test/mcp")).toBe(false);
    expect(isAllowedMcpServerUrl("https://169.254.169.254/latest")).toBe(false);
    expect(isAllowedMcpServerUrl("ftp://mcp.example/mcp")).toBe(false);
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
