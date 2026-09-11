import { afterEach, describe, expect, it } from "vitest";
import { isRootAuthRequired } from "./root-auth";

describe("isRootAuthRequired", () => {
  const key = "DIGICHAT_REQUIRE_ROOT_AUTH";

  afterEach(() => {
    delete process.env[key];
  });

  it("defaults OFF when unset", () => {
    delete process.env[key];
    expect(isRootAuthRequired()).toBe(false);
  });

  it("is OFF for 0 / false / empty", () => {
    process.env[key] = "0";
    expect(isRootAuthRequired()).toBe(false);
    process.env[key] = "false";
    expect(isRootAuthRequired()).toBe(false);
    process.env[key] = "";
    expect(isRootAuthRequired()).toBe(false);
  });

  it("is ON for 1 / true / on", () => {
    process.env[key] = "1";
    expect(isRootAuthRequired()).toBe(true);
    process.env[key] = "true";
    expect(isRootAuthRequired()).toBe(true);
    process.env[key] = "ON";
    expect(isRootAuthRequired()).toBe(true);
  });
});
