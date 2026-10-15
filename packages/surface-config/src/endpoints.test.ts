import { expect, test } from "bun:test";
import { endpoint } from "./endpoints";

test("local chat defaults to :3000", () => {
  expect(endpoint("chat", {})).toBe("http://127.0.0.1:3000");
});

test("DIGI_CHAT_URL wins over aliases and defaults", () => {
  expect(
    endpoint("chat", {
      DIGI_CHAT_URL: "http://127.0.0.1:3005/",
      DIGICHAT_DEVKIT_URL: "http://127.0.0.1:3999",
    }),
  ).toBe("http://127.0.0.1:3005");
});

test("DIGICHAT_DEVKIT_URL is a deprecated chat alias", () => {
  expect(endpoint("chat", { DIGICHAT_DEVKIT_URL: "http://127.0.0.1:3005" })).toBe(
    "http://127.0.0.1:3005",
  );
});

test("DQ_API_URL is desk-only and does not set chat", () => {
  expect(endpoint("chat", { DQ_API_URL: "http://127.0.0.1:8788" })).toBe("http://127.0.0.1:3000");
  expect(endpoint("desk", { DQ_API_URL: "http://127.0.0.1:8788/" })).toBe("http://127.0.0.1:8788");
});

test("cloud chat uses digithings.ai; cloud mcp stays unset", () => {
  expect(endpoint("chat", { DIGI_ENV: "cloud" })).toBe("https://digithings.ai");
  expect(() => endpoint("mcp", { DIGI_ENV: "cloud" })).toThrow(/unset/);
});
