// @vitest-environment happy-dom
/**
 * Safari-compatible block caret for the gallery-thread composer.
 *
 * `caret-shape: block` is Chromium-only, so on other engines a painted block
 * span tracks the native caret (which is made transparent via CSS). Row/col is
 * a pure function of the textarea value + selection offset — the overlay only
 * positions a span from those numbers.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { caretRowCol, ComposerBlockCaret } from "./block-caret";

function mount(ui: React.ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => {
    root.render(ui);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

describe("caretRowCol", () => {
  it("starts at row 0 col 0 in empty text", () => {
    expect(caretRowCol("", 0)).toEqual({ row: 0, col: 0 });
  });

  it("counts columns on a single line", () => {
    expect(caretRowCol("hello", 2)).toEqual({ row: 0, col: 2 });
    expect(caretRowCol("hello", 5)).toEqual({ row: 0, col: 5 });
  });

  it("counts rows and columns across newlines", () => {
    expect(caretRowCol("ab\ncde", 0)).toEqual({ row: 0, col: 0 });
    expect(caretRowCol("ab\ncde", 3)).toEqual({ row: 1, col: 0 });
    expect(caretRowCol("ab\ncde", 5)).toEqual({ row: 1, col: 2 });
  });

  it("clamps offsets outside the text", () => {
    expect(caretRowCol("hi", 99)).toEqual({ row: 0, col: 2 });
    expect(caretRowCol("hi", -4)).toEqual({ row: 0, col: 0 });
  });
});

describe("ComposerBlockCaret", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function mountWithInput(value: string, selection: number) {
    let area: HTMLTextAreaElement | null = null;
    const containerRef = {
      get current(): HTMLDivElement | null {
        return document.querySelector("div[data-caret-fixture]") as HTMLDivElement | null;
      },
    };
    const { host, unmount } = mount(
      <div data-caret-fixture>
        <textarea
          ref={(el) => {
            area = el;
            if (el) {
              el.value = value;
              el.setSelectionRange(selection, selection);
            }
          }}
        />
        <ComposerBlockCaret containerRef={containerRef as never} />
      </div>,
    );
    return { host, unmount, area: () => area as HTMLTextAreaElement };
  }

  it("positions the block at the initial caret offset", () => {
    const { host, unmount } = mountWithInput("hello", 2);
    const block = host.querySelector<HTMLElement>('[data-slot="aui_block-caret"]');
    expect(block).not.toBeNull();
    expect(block?.style.getPropertyValue("--caret-col")).toBe("2");
    expect(block?.style.getPropertyValue("--caret-row")).toBe("0");
    unmount();
  });

  it("tracks the caret across lines on select events", () => {
    const { host, unmount, area } = mountWithInput("ab\ncde", 0);
    const block = host.querySelector<HTMLElement>('[data-slot="aui_block-caret"]');
    act(() => {
      area().setSelectionRange(5, 5);
      area().dispatchEvent(new Event("select", { bubbles: true }));
    });
    expect(block?.style.getPropertyValue("--caret-col")).toBe("2");
    expect(block?.style.getPropertyValue("--caret-row")).toBe("1");
    unmount();
  });

  it("updates the column as text is typed", () => {
    const { host, unmount, area } = mountWithInput("", 0);
    const block = host.querySelector<HTMLElement>('[data-slot="aui_block-caret"]');
    act(() => {
      area().value = "hey";
      area().setSelectionRange(3, 3);
      area().dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(block?.style.getPropertyValue("--caret-col")).toBe("3");
    unmount();
  });

  it("is aria-hidden so it never enters the accessibility tree", () => {
    const { host, unmount } = mountWithInput("x", 1);
    expect(
      host.querySelector('[data-slot="aui_block-caret"]')?.getAttribute("aria-hidden"),
    ).toBe("true");
    unmount();
  });
});
