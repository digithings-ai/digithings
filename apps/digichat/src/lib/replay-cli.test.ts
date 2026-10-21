import { describe, expect, it } from "vitest";
import { conversationReplayUrl, parseReplayCli } from "./replay-cli";

describe("parseReplayCli", () => {
  it("builds a conversation request without printing the credential", () => {
    const parsed = parseReplayCli(["--id", "conv 1", "--out", "out.html", "--theme", "light"], {
      DIGICHAT_URL: "http://127.0.0.1:3005/",
      DIGICHAT_API_KEY: "dgk_live_TESTSECRET99",
    });
    expect(parsed.ok).toBe(true);
    if (!parsed.ok || parsed.plan.mode !== "conversation") return;
    expect(parsed.plan.id).toBe("conv 1");
    expect(parsed.plan.out).toBe("out.html");
    expect(parsed.plan.baseUrl).toBe("http://127.0.0.1:3005");
    expect(parsed.plan.authorization).toBe("Bearer dgk_live_TESTSECRET99");
    expect(parsed.plan.theme).toBe("light");
    const url = conversationReplayUrl(parsed.plan);
    expect(url).toBe("http://127.0.0.1:3005/api/conversations/conv%201/replay?theme=light");
    expect(url).not.toContain("dgk_live_");
  });

  it("accepts --fixture and rejects mixing it with --id", () => {
    expect(parseReplayCli(["--fixture"], {}).ok).toBe(true);
    const mixed = parseReplayCli(["--fixture", "--id", "c"], {});
    expect(mixed.ok).toBe(false);
  });
});
