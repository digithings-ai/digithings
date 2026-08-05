import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { mapDigivaultNdjsonEvent } from "./digivault-ndjson-adapter";
import { sanitizeActivitySpan, type ActivitySpan } from "./chat-activity";
import { buildToolContext, type VaultHit } from "./digivault-vault";

const FIXTURE_DIR = join(__dirname, "fixtures/digivault");

describe("digivault fixture parity", () => {
  it("matches golden activity sequence for recorded CF turn", () => {
    const ndjson = readFileSync(join(FIXTURE_DIR, "sample-turn.ndjson"), "utf8");
    const events = ndjson
      .trim()
      .split("\n")
      .map((l) => JSON.parse(l) as unknown);
    const spans: ActivitySpan[] = [];
    let text = "";
    for (const ev of events) {
      const mapped = mapDigivaultNdjsonEvent(ev);
      if (!mapped) continue;
      if (mapped.type === "text-delta") text += mapped.delta;
      if (mapped.type === "activity") {
        const s = sanitizeActivitySpan(mapped.span);
        if (s) spans.push(s);
      }
    }
    const golden = JSON.parse(
      readFileSync(join(FIXTURE_DIR, "sample-turn.golden.json"), "utf8"),
    ) as { spans: ActivitySpan[]; text: string };
    expect(spans).toEqual(golden.spans);
    expect(text).toBe(golden.text);
  });

  it("vault RPC fixture keeps body out of activity documents", () => {
    const hits: VaultHit[] = [
      {
        vault_path: "arch/ports.md",
        title: "Ports",
        body_markdown: "# secret body from vault RPC",
      },
    ];
    const { toolText, activityDocuments } = buildToolContext(hits);
    expect(toolText).toContain("secret body");
    expect(JSON.stringify(activityDocuments)).not.toContain("secret body");
    expect(JSON.stringify(activityDocuments)).not.toContain("body_markdown");
    expect(activityDocuments).toEqual([{ title: "Ports", path: "arch/ports.md" }]);
  });
});
