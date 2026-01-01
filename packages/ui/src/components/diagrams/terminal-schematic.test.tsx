import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { TerminalSchematic } from "./TerminalSchematic";

describe("TerminalSchematic", () => {
  const html = renderToStaticMarkup(
    <TerminalSchematic
      title="digichat · rag loop"
      label="digichat rag loop. not a live run"
      legend={[
        { tone: "main", label: "main step" },
        { tone: "model", label: "model step" },
        { tone: "ok", label: "ok" },
      ]}
      rows={[
        { nodes: [{ label: "digichat", tone: "main" }] },
        {
          nodes: [
            { label: "digisearch", tone: "side" },
            { label: "digillm", tone: "model" },
          ],
        },
      ]}
      loop="ask again until the answer is enough"
      notes={["digichat asks", "recall and the model run together"]}
      receipt={["digichat · question", "digisearch · recall"]}
    />,
  );

  it("draws the stack, the loop, the legend, and the receipt up front", () => {
    expect(html).toContain("digichat");
    expect(html).toContain("digisearch");
    expect(html).toContain("in parallel");
    expect(html).toContain("ask again until the answer is enough");
    expect(html).toContain("main step");
    expect(html).toContain("digichat · question");
    expect(html).toContain("not a live run");
    expect(html).toContain("threads");
    expect(html).not.toMatch(/Grokopedia|Claude|Jev|Opus|Fable/);
  });
});
