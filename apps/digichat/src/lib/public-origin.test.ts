import { describe, expect, it } from "vitest";
import { publicOrigin } from "./public-origin";

describe("publicOrigin", () => {
  it("returns the origin of a production URL", () => {
    expect(publicOrigin("https://digithings.ai")?.href).toBe("https://digithings.ai/");
    expect(publicOrigin(" https://digithings.ai/chat/ ")?.href).toBe("https://digithings.ai/");
  });

  it("is undefined when unset, blank or not http(s)", () => {
    expect(publicOrigin(undefined)).toBeUndefined();
    expect(publicOrigin("   ")).toBeUndefined();
    expect(publicOrigin("not a url")).toBeUndefined();
    expect(publicOrigin("javascript:alert(1)")).toBeUndefined();
  });
});
