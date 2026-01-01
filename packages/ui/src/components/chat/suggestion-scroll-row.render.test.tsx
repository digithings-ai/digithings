// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

import { SuggestionScrollRow } from "./suggestion-scroll-row";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("SuggestionScrollRow", () => {
  it("marks the row as scrolling for a moment so its thin bar shows", () => {
    vi.useFakeTimers();
    const onScroll = vi.fn();
    const { getByTestId } = render(
      <SuggestionScrollRow data-testid="row" className="w-full" onScroll={onScroll}>
        <span>chip</span>
      </SuggestionScrollRow>,
    );
    const row = getByTestId("row");
    expect(row.className).toContain("aui-suggestion-scroll");
    expect(row.className).toContain("overflow-x-auto");
    expect(row.dataset.scrolling).toBeUndefined();

    fireEvent.scroll(row);
    expect(row.dataset.scrolling).toBe("true");
    expect(onScroll).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1000);
    expect(row.dataset.scrolling).toBeUndefined();
  });

  it("shows the bar while a mouse is over the row or a chip has focus", () => {
    const { getByTestId, getByText } = render(
      <SuggestionScrollRow data-testid="row">
        <button type="button">chip</button>
      </SuggestionScrollRow>,
    );
    const row = getByTestId("row");
    fireEvent.pointerEnter(row, { pointerType: "mouse" });
    expect(row.dataset.hover).toBe("true");
    fireEvent.pointerLeave(row, { pointerType: "mouse" });
    expect(row.dataset.hover).toBeUndefined();
    fireEvent.focus(getByText("chip"));
    expect(row.dataset.focus).toBe("true");
    fireEvent.blur(getByText("chip"));
    expect(row.dataset.focus).toBeUndefined();
  });

  it("keeps the bar thin and transparent at rest in the shared chat sheet", () => {
    const css = readFileSync(resolve(__dirname, "../../styles/chat-aui.css"), "utf8");
    expect(css).toMatch(/\.aui-suggestion-scroll::-webkit-scrollbar \{[^}]*height: 4px/);
    expect(css).toMatch(/\.aui-suggestion-scroll::-webkit-scrollbar-thumb \{[^}]*background: transparent/);
    expect(css).toContain(".aui-suggestion-scroll[data-scrolling]::-webkit-scrollbar-thumb");
  });

  it("is the scroll row for the example questions in every skin", () => {
    for (const file of [
      "skins/base/thread.tsx",
      "stock/follow-up-suggestions.aui.tsx",
      "gallery-thread/follow-up-suggestions.aui.tsx",
    ]) {
      const src = readFileSync(resolve(__dirname, file), "utf8");
      expect(src, file).toContain("<SuggestionScrollRow");
      expect(src, file).not.toContain("scrollbar-none");
    }
  });
});
