// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChatStatusNotice } from "./chat-notice";
import { JsonView } from "./json-view";
import { StockShapeProvider } from "./stock-shape";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

// Shared stock pieces (button, textarea, notices, JSON dumps) are also used by
// other skins. Outside the stock Thread they keep the square house radius;
// inside it they take assistant-ui's default radius.
afterEach(() => {
  cleanup();
});

function classesOf(ui: React.ReactElement, stock: boolean): string[] {
  const { container } = render(stock ? <StockShapeProvider>{ui}</StockShapeProvider> : ui);
  return (container.firstElementChild?.getAttribute("class") ?? "").split(/\s+/);
}

const CASES: { name: string; ui: () => React.ReactElement; upstream: string }[] = [
  { name: "button (default size)", ui: () => <Button>Go</Button>, upstream: "rounded-lg" },
  {
    name: "button (sm)",
    ui: () => <Button size="sm">Go</Button>,
    upstream: "rounded-[min(var(--radius-md),12px)]",
  },
  { name: "textarea", ui: () => <Textarea />, upstream: "rounded-lg" },
  { name: "status notice", ui: () => <ChatStatusNotice message="Waiting" />, upstream: "rounded-md" },
  { name: "JSON view", ui: () => <JsonView value={{ a: 1 }} />, upstream: "rounded-md" },
];

describe("stock shape", () => {
  for (const c of CASES) {
    it(`${c.name}: square outside the stock Thread`, () => {
      const cls = classesOf(c.ui(), false);
      expect(cls).toContain("rounded-none");
      expect(cls).not.toContain(c.upstream);
    });

    it(`${c.name}: assistant-ui radius inside the stock Thread`, () => {
      const cls = classesOf(c.ui(), true);
      expect(cls).toContain(c.upstream);
      expect(cls).not.toContain("rounded-none");
    });
  }

  it("a caller's own radius still wins inside the stock Thread", () => {
    const cls = classesOf(<Button className="rounded-full">Go</Button>, true);
    expect(cls).toContain("rounded-full");
    expect(cls).not.toContain("rounded-lg");
  });
});
