import { describe, expect, it } from "vitest";
import { remarkStripModelBoilerplate, stripModelBoilerplate } from "./strip-model-boilerplate";

const LEAK =
  "Use the results below to formulate an answer to the user question unless additional information is needed";

describe("stripModelBoilerplate", () => {
  it("removes the doubled DeepSeek search-template line", () => {
    expect(stripModelBoilerplate(`${LEAK}.${LEAK}`)).toBe("");
    expect(stripModelBoilerplate(`Intro. ${LEAK}. Answer`)).toBe("Intro. Answer");
  });
  it("leaves normal text alone", () => {
    expect(stripModelBoilerplate("Use the help article below.")).toBe("Use the help article below.");
  });
  it("cleans text nodes in a markdown tree", () => {
    const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: `${LEAK}${LEAK}` }] }] };
    remarkStripModelBoilerplate()(tree);
    expect(tree.children[0].children[0].value).toBe("");
  });
});

describe("stripModelBoilerplate repeats and truncations", () => {
  it("removes dozens of concatenated copies", () => {
    expect(stripModelBoilerplate(LEAK.repeat(30))).toBe("");
    expect(stripModelBoilerplate(`${LEAK}. ${LEAK}.\n${LEAK}`)).toBe("");
  });
  it("removes a trailing partial copy", () => {
    expect(stripModelBoilerplate(`Answer.${LEAK}${LEAK.slice(0, 40)}`)).toBe("Answer.");
    expect(stripModelBoilerplate(`Answer. Use the results below to formul`)).toBe("Answer.");
  });
  it("keeps text around repeats", () => {
    expect(stripModelBoilerplate(`Intro.${LEAK}${LEAK} Body.`)).toBe("Intro. Body.");
  });
  it("handles line-wrapped copies", () => {
    expect(stripModelBoilerplate(LEAK.replace(/ to /g, "\nto "))).toBe("");
  });
});
