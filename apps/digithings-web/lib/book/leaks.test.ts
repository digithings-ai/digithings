import { describe, expect, it } from "vitest";

import { findLeaks } from "./leaks";

const rules = (s: string) => findLeaks(s).map((l) => l.rule);

describe("findLeaks", () => {
  it("flags env names, loopback hosts, ports and secret words", () => {
    expect(rules("set OPENAI_API_BASE first")).toEqual(["env-name"]);
    expect(rules("open http://localhost/ now")).toEqual(["loopback"]);
    expect(rules("digigraph :8000 serves it")).toEqual(["port"]);
    expect(rules("the stack listens on host:4000")).toEqual(["port"]);
    expect(rules("rotate the API key monthly")).toEqual(["secret-word"]);
  });

  it("leaves high-level prose alone", () => {
    expect(rules("MCP and OpenTelemetry are open standards, at 12 o'clock.")).toEqual([]);
    expect(rules("Self-host it on your own machine or on Cloudflare.")).toEqual([]);
  });

  it("exempts frontmatter, link targets and Reference hrefs", () => {
    expect(rules("---\ntitle: X_Y_Z\n---\nbody")).toEqual([]);
    expect(rules("[self-host guide](https://github.com/o/r/blob/develop/docs/LOCAL_STACK.md)")).toEqual([]);
    expect(rules('<Reference href="https://x.test/SELF_HOST.md" title="Self-hosting" />')).toEqual([]);
  });

  it("honours an explicit, reasoned allow comment", () => {
    expect(rules("see :8000 {/* book-lint-allow: quoting the spec */}")).toEqual([]);
  });
});
