import { describe, expect, it } from "vitest";
import { fixtureDocument, fixtureMessages } from "./fixture";
import { messagesToReplay, type ReplayChromeInput } from "./from-messages";

const JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";

const chrome: ReplayChromeInput = {
  deployment: "North Wind",
  title: "Northwind",
  welcome: "Desk",
  suggestions: ["Ask"],
  theme: { preference: "auto", resolved: "dark", palette: "default", view: "verbose" },
};

describe("messagesToReplay", () => {
  it("pairs questions with reasoning, tool cards, notices, and answers", () => {
    const doc = fixtureDocument();
    expect(doc.deployment).toBe("northwind");
    expect(doc.turns).toHaveLength(2);
    expect(doc.turns[0]?.userText).toBe("What moved in the book overnight?");
    const chain = doc.turns[0]?.blocks.find((block) => block.kind === "chain");
    expect(chain?.kind).toBe("chain");
    if (chain?.kind !== "chain") return;
    expect(chain.items.map((item) => item.kind)).toEqual(["reasoning", "tool"]);
    const tool = chain.items[1];
    if (tool?.kind !== "tool") throw new Error("expected a tool");
    expect(tool.tool.name).toBe("digisearch");
    expect(tool.tool.argsText).toContain("overnight book changes");
    expect(tool.tool.resultText).toContain("Copper hedge was lifted");
    const notice = doc.turns[1]?.blocks.find((block) => block.kind === "chain");
    expect(JSON.stringify(notice)).toContain("research corpus");
    expect(doc.suggestions).toEqual(["What moved in the book?", "Walk through the copper hedge"]);
  });

  it("reads assistant-ui tool-call content as well as AI SDK parts", () => {
    const doc = messagesToReplay(
      [
        { id: "u", role: "user", content: "status?" },
        {
          id: "a",
          role: "assistant",
          content: [
            {
              type: "tool-call",
              toolName: "digivault",
              args: { path: "notes/close.md" },
              result: { hit: true },
            },
            { type: "text", text: "The note is there." },
          ],
        },
      ],
      chrome,
      "2026-10-21T00:00:00.000Z",
    );
    const tool = doc.turns[0]?.blocks[0];
    expect(tool?.kind).toBe("chain");
    if (tool?.kind !== "chain") return;
    const card = tool.items[0];
    expect(card?.kind).toBe("tool");
    if (card?.kind !== "tool") return;
    expect(card.tool.name).toBe("digivault");
    expect(card.tool.argsText).toContain("notes/close.md");
    expect(card.tool.resultText).toContain("true");
  });

  it("strips tokens, embed keys, invite keys, and auth headers before the document exists", () => {
    const doc = messagesToReplay(
      [
        {
          id: "u",
          role: "user",
          parts: [{ type: "text", text: "key dgk_live_TESTSECRET99 and ?token=query-plain-9f3c2a" }],
        },
        {
          id: "a",
          role: "assistant",
          parts: [
            {
              type: "tool-digisearch",
              state: "output-available",
              input: { authorization: `Bearer ${JWT}`, q: "book" },
              output: {
                api_key: "sk-ant-TESTSECRET99",
                inviteKey: "invite-plain-9f3c2a",
                note: "X-Embed-Token: embed-plain-9f3c2a",
              },
            },
            { type: "text", text: "digi_live_TESTSECRET99 stays out of the file" },
          ],
        },
      ],
      chrome,
      "2026-10-21T00:00:00.000Z",
    );
    const flat = JSON.stringify(doc);
    for (const secret of [
      "dgk_live_TESTSECRET99",
      "digi_live_TESTSECRET99",
      "sk-ant-TESTSECRET99",
      "invite-plain-9f3c2a",
      "embed-plain-9f3c2a",
      "query-plain-9f3c2a",
      JWT,
    ]) {
      expect(flat).not.toContain(secret);
    }
    expect(flat).toContain("[redacted]");
    expect(flat).toContain("book");
  });

  it("ignores the fixture's own messages as a control", () => {
    expect(JSON.stringify(fixtureMessages)).not.toContain("dgk_live_");
  });
});
