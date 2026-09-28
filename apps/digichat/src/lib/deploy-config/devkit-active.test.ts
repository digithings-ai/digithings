import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getDevkitActiveConfig,
  parseDevkitConfigParam,
  setDevkitActiveConfig,
} from "./devkit-active";
import {
  getDigichatConfig,
  resetDigichatConfigForTests,
  setDigichatConfigForTests,
} from "./loader";

afterEach(() => {
  setDevkitActiveConfig(null);
  resetDigichatConfigForTests();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("parseDevkitConfigParam", () => {
  it("accepts a bare *.yaml filename", () => {
    expect(parseDevkitConfigParam("demo.yaml")).toBe("demo.yaml");
    expect(parseDevkitConfigParam(["demo.yaml"])).toBe("demo.yaml");
  });

  it("clears on absent, empty, or explicit clear", () => {
    expect(parseDevkitConfigParam(undefined)).toBeNull();
    expect(parseDevkitConfigParam("")).toBeNull();
    expect(parseDevkitConfigParam("clear")).toBeNull();
  });

  it("accepts a nested examples/ filename", () => {
    expect(parseDevkitConfigParam("examples/demo.yaml")).toBe("examples/demo.yaml");
  });

  it("rejects traversal, absolute-ish paths, and non-yaml (kept unchanged by callers)", () => {
    expect(parseDevkitConfigParam("../secrets.yaml")).toBeUndefined();
    expect(parseDevkitConfigParam("examples/../secrets.yaml")).toBeUndefined();
    expect(parseDevkitConfigParam("a/b/c/../../../x.yaml")).toBeUndefined();
    expect(parseDevkitConfigParam("/etc/passwd.yaml")).toBeUndefined();
    expect(parseDevkitConfigParam("demo.yml")).toBeUndefined();
    expect(parseDevkitConfigParam("demo.txt")).toBeUndefined();
  });
});

describe("devkit active config override", () => {
  it("serves the overridden file through getDigichatConfig (dev only)", () => {
    setDevkitActiveConfig("datatap-trial-test.yaml");
    expect(getDevkitActiveConfig()).toBe("datatap-trial-test.yaml");
    expect(getDigichatConfig().deployment?.slug).toBe("datatap-trial-test");
  });

  it("falls back to the singleton when the override file fails to load", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    setDigichatConfigForTests({
      version: 1,
      deployment: {
        slug: "singleton",
        backend: { type: "digigraph" },
        chrome: { mode: "embed", theme: "dark", skin: "digichat" },
      },
    } as never);
    setDevkitActiveConfig("definitely-missing-file.yaml");
    expect(getDigichatConfig().deployment?.slug).toBe("singleton");
    expect(warn).toHaveBeenCalled();
  });

  it("is never consulted in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    setDigichatConfigForTests({
      version: 1,
      deployment: {
        slug: "prod-singleton",
        backend: { type: "digigraph" },
        chrome: { mode: "embed", theme: "dark", skin: "digichat" },
      },
    } as never);
    setDevkitActiveConfig("datatap-trial-test.yaml");
    expect(getDigichatConfig().deployment?.slug).toBe("prod-singleton");
  });

  it("returns to the singleton when cleared", () => {
    setDevkitActiveConfig("datatap-trial-test.yaml");
    expect(getDigichatConfig().deployment?.slug).toBe("datatap-trial-test");
    setDevkitActiveConfig(null);
    expect(getDevkitActiveConfig()).toBeNull();
  });
});
