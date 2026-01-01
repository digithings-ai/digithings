// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BlockBoundary, StateBlock } from "./StateBlock";

afterEach(cleanup);

const state = () => screen.getByText(/^\[/).closest("[data-state]");

describe("StateBlock", () => {
  it("announces loading and stops its spinner under reduced motion", () => {
    const { container } = render(<StateBlock kind="loading" />);
    const block = container.querySelector('[data-state="loading"]');
    expect(block?.getAttribute("role")).toBe("status");
    expect(block?.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Loading.")).toBeTruthy();
    expect(container.querySelector(".animate-spin")?.className).toContain(
      "motion-reduce:animate-none",
    );
  });

  it("names an empty state and why it is empty", () => {
    render(
      <StateBlock kind="empty" title="No positions." reason="the book has not been marked today" />,
    );
    expect(state()?.getAttribute("data-state")).toBe("empty");
    expect(screen.getByText("No positions.")).toBeTruthy();
    expect(screen.getByText("the book has not been marked today")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not identify an error by colour alone", () => {
    render(<StateBlock kind="error" reason="/portfolio: 502 from the api" />);
    expect(state()?.getAttribute("data-state")).toBe("error");
    // a live-region announcement, a text marker, and the danger tone — any one
    // of the three survives a reader who cannot see the colour.
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("[!]")).toBeTruthy();
    const title = screen.getByText("Could not load.");
    expect(title.className).toContain("text-danger");
    expect(title.className).not.toContain("text-ink-soft");
  });

  it("withholds a figure and says why, without calling it an error", () => {
    render(<StateBlock kind="withheld" reason="/ledger: sample too thin to publish" />);
    expect(state()?.getAttribute("data-state")).toBe("withheld");
    expect(screen.getByText("[withheld]")).toBeTruthy();
    expect(screen.getByText("Withheld.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers a retry as a real, keyboard-reachable button", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<StateBlock kind="error" onRetry={onRetry} retryLabel="try again" />);
    const button = screen.getByRole("button", { name: "try again" });
    button.focus();
    expect(document.activeElement).toBe(button);
    expect(button.className).toContain("cursor-pointer");
    await user.keyboard("{Enter}");
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders no retry when none is offered", () => {
    render(<StateBlock kind="withheld" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("BlockBoundary", () => {
  const Boom = (): never => {
    throw new Error("columns is not an array");
  };

  it("replaces a thrown block with a withheld state, not a broken page", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <div>
        <p>portfolio</p>
        <BlockBoundary label="/portfolio">
          <Boom />
        </BlockBoundary>
      </div>,
    );
    expect(screen.getByText("portfolio")).toBeTruthy();
    expect(screen.getByText("Withheld.")).toBeTruthy();
    expect(
      screen.getByText("/portfolio: unexpected response shape (columns is not an array)"),
    ).toBeTruthy();
    spy.mockRestore();
  });

  it("renders its children untouched when they do not throw", () => {
    render(
      <BlockBoundary label="/portfolio">
        <p>book · allocation</p>
      </BlockBoundary>,
    );
    expect(screen.getByText("book · allocation")).toBeTruthy();
    expect(screen.queryByText("Withheld.")).toBeNull();
  });
});
