// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StockShapeProvider } from "../stock-shape";
import { Dialog, DialogContent, DialogTitle } from "./dialog";

// The dialog is portaled to <body>, out of the stock thread's subtree, so it
// marks itself for chat-aui.css's scoped `bg-surface-2` (DIG-6110) only when
// it is opened from inside the stock thread.
function OpenDialog() {
  return (
    <Dialog open>
      <DialogContent>
        <DialogTitle>Preview</DialogTitle>
      </DialogContent>
    </Dialog>
  );
}

afterEach(cleanup);

describe("stock dialog portal marker", () => {
  it("marks the dialog opened inside the stock thread", () => {
    render(
      <StockShapeProvider>
        <OpenDialog />
      </StockShapeProvider>,
    );
    const content = document.body.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content!.hasAttribute("data-stock-portal")).toBe(true);
  });

  it("leaves a dialog opened elsewhere unmarked", () => {
    render(<OpenDialog />);
    const content = document.body.querySelector('[data-slot="dialog-content"]');
    expect(content).not.toBeNull();
    expect(content!.hasAttribute("data-stock-portal")).toBe(false);
  });
});
