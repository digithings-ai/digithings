import { describe, expect, it } from "vitest";

import { escapeUnsafeChars } from "./escape-unsafe-chars";

describe("escapeUnsafeChars", () => {
  it("escapes angle brackets that could close the surrounding script tag", () => {
    expect(escapeUnsafeChars('"</script><img src=x onerror=alert(1)>"')).toBe(
      '"\\u003C/script\\u003E\\u003Cimg src=x onerror=alert(1)\\u003E"',
    );
  });

  it("escapes the U+2028 and U+2029 line separators", () => {
    expect(escapeUnsafeChars("a\u2028b\u2029c")).toBe("a\\u2028b\\u2029c");
  });

  it("leaves backslashes and forward slashes untouched", () => {
    const json = JSON.stringify({ path: "a\\b/c" });
    expect(escapeUnsafeChars(json)).toBe(json);
  });

  it("leaves ordinary JSON.stringify output unchanged", () => {
    const json = JSON.stringify({ id: "one", values: [1, 2, 3] });
    expect(escapeUnsafeChars(json)).toBe(json);
  });
});
