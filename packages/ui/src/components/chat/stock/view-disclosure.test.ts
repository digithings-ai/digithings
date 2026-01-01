import { describe, expect, it } from "vitest";
import { DEFAULT_DEPLOY_UI, viewDisclosure } from "./deploy-ui-context";

describe("viewDisclosure (/view in the base and chatgpt skins)", () => {
  it("the default deployment keeps today's folded layout", () => {
    const d = viewDisclosure(DEFAULT_DEPLOY_UI);
    expect([d.toolGroupOpen, d.toolCardOpen]).toEqual([false, false]);
  });
  it("quiet folds everything, even thinking while it streams", () => {
    const d = viewDisclosure({ view: "quiet", toolCalls: "collapsed", reasoning: "balanced" });
    expect([d.toolGroupOpen, d.toolCardOpen, d.reasoningOpen(true)]).toEqual([false, false, false]);
  });
  it("balanced opens thinking only while it streams", () => {
    const d = viewDisclosure({ view: "balanced", toolCalls: "balanced", reasoning: "balanced" });
    expect([d.toolGroupOpen, d.reasoningOpen(true), d.reasoningOpen(false)]).toEqual([false, true, false]);
  });
  it("verbose opens the group and the cards", () => {
    const d = viewDisclosure({ view: "verbose", toolCalls: "expanded", reasoning: "expanded" });
    expect([d.toolGroupOpen, d.toolCardOpen, d.reasoningOpen(false)]).toEqual([true, true, true]);
  });
  it("the remount key changes with the level so a /view switch applies to rendered messages", () => {
    const a = viewDisclosure({ view: "quiet", toolCalls: "collapsed", reasoning: "collapsed" }).key;
    const b = viewDisclosure({ view: "verbose", toolCalls: "expanded", reasoning: "collapsed" }).key;
    expect(a).not.toBe(b);
  });
});
