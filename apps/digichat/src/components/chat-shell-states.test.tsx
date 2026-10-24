// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  ChatShellEmpty,
  ChatShellLoading,
  ChatShellUnavailable,
} from "./chat-shell-states";

/** Audit T4: the app shell's states are designed, not dropped. */
describe("chat shell states", () => {
  it("waits on the house type-out instead of a bare spinner", () => {
    const { container } = render(<ChatShellLoading />);
    expect(
      container.querySelector(".app-shell-wait")?.getAttribute("aria-busy"),
    ).toBe("true");
    expect(container.textContent).toBeTruthy();
    expect(container.textContent).not.toContain("Loading…");
    expect(container.querySelector(".animate-spin")).toBeNull();
  });

  it("runs the real phases of the wait", () => {
    const { container } = render(<ChatShellLoading />);
    expect(container.querySelector(".tl-boot-title")?.textContent).toBe("digichat");
    expect(
      container.querySelectorAll(".tl-line").length,
    ).toBeGreaterThan(0);
  });

  it("names the empty sidebar reason", () => {
    const { rerender } = render(<ChatShellEmpty query="" />);
    expect(screen.getByRole("status").textContent).toContain("No chats yet.");
    rerender(<ChatShellEmpty query="zammad" />);
    expect(screen.getByRole("status").textContent).toContain(
      "No chats match that search.",
    );
  });

  it("marks the failed thread as an alert and offers retry", () => {
    const onRetry = vi.fn();
    render(<ChatShellUnavailable onRetry={onRetry} />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Could not load this conversation.",
    );
    fireEvent.click(screen.getByRole("button", { name: "retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
