// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

/**
 * The parts the chain describes, and the reason this test stubs
 * `@assistant-ui/react`: the header only reads `message.parts`, so a plain
 * object is a truer fixture than a mounted runtime.
 */
const aui = vi.hoisted(() => ({
  parts: [] as readonly WorkStatusPart[],
  status: undefined as { type: string; reason?: string } | undefined,
  threadRunning: false,
}));

type StubState = {
  message: { parts: readonly WorkStatusPart[] };
  optional: { message?: { status?: { type: string; reason?: string } }; thread?: { isRunning: boolean } };
};

vi.mock("@assistant-ui/react", () => ({
  useAuiState: <T,>(selector: (state: StubState) => T) =>
    selector({
      message: { parts: aui.parts },
      optional: {
        ...(aui.status ? { message: { status: aui.status } } : {}),
        thread: { isRunning: aui.threadRunning },
      },
    }),
}));

import { WorkChain } from "./work-chain";
import { workStatusText, type WorkStatusPart } from "./work-status";

afterEach(() => {
  cleanup();
  aui.status = undefined;
  aui.threadRunning = false;
});

const runningTool = (toolName: string) => ({
  type: "tool-call",
  toolName,
  toolCallId: `call-${toolName}`,
  argsText: "{}",
  status: { type: "running" },
});

const doneTool = (toolName: string) => ({
  type: "tool-call",
  toolName,
  toolCallId: `call-${toolName}`,
  argsText: "{}",
  result: "ok",
  status: { type: "complete" },
});

const runningReasoning = { type: "reasoning", text: "…", status: { type: "running" } };
const doneReasoning = { type: "reasoning", text: "thought", status: { type: "complete" } };
const answer = { type: "text", text: "grounded answer" };

function headerText(container: HTMLElement): string | null {
  return container.querySelector('[data-slot="aui_work-status-label"]')?.textContent ?? null;
}

describe("workStatusText", () => {
  it("names the tool that is running", () => {
    aui.parts = [doneTool("digisearch"), runningTool("digivault_search_notes")];
    expect(workStatusText(aui.parts, [0, 1])).toEqual({
      label: "Working — digivault_search_notes",
      running: true,
    });
  });

  it("says thinking while only the reasoning runs", () => {
    aui.parts = [runningReasoning];
    expect(workStatusText(aui.parts, [0])).toEqual({ label: "Thinking", running: true });
  });

  it("counts the tools once the work is done", () => {
    aui.parts = [doneTool("digisearch")];
    expect(workStatusText(aui.parts, [0])).toEqual({
      label: "Used 1 tool",
      running: false,
    });
    aui.parts = [doneTool("digisearch"), doneTool("digivault_search_notes")];
    expect(workStatusText(aui.parts, [0, 1])).toEqual({
      label: "Used 2 tools",
      running: false,
    });
  });

  it("says it thought when the chain only reasoned", () => {
    aui.parts = [doneReasoning];
    expect(workStatusText(aui.parts, [0])).toEqual({ label: "Thought", running: false });
  });

  it("reads only the indices it is given", () => {
    // A second chain's running tool must not leak into the first chain.
    aui.parts = [doneTool("digisearch"), runningTool("digivault_search_notes")];
    expect(workStatusText(aui.parts, [0]).label).toBe("Used 1 tool");
  });
});

describe("WorkChain header", () => {
  it("is a live status line while the chain is folded", () => {
    aui.parts = [runningTool("digisearch"), answer];
    const { container } = render(
      <WorkChain indices={[0, 1]} followedByText>
        <div>chain</div>
      </WorkChain>,
    );
    expect(headerText(container)).toBe("Working — digisearch");
  });

  it("counts the work once a folded chain is done", () => {
    aui.parts = [doneTool("digisearch"), doneTool("digivault_search_notes"), answer];
    const { container } = render(
      <WorkChain indices={[0, 1, 2]} followedByText>
        <div>chain</div>
      </WorkChain>,
    );
    expect(headerText(container)).toBe("Used 2 tools");
  });

  it("keeps the plain title while the chain is expanded", () => {
    aui.parts = [runningTool("digisearch")];
    const expanded = render(
      <WorkChain indices={[0]} openAtRest>
        <div>chain</div>
      </WorkChain>,
    );
    expect(headerText(expanded.container)).toBe("Working");
    expanded.unmount();

    aui.parts = [doneTool("digisearch"), answer];
    const done = render(
      <WorkChain indices={[0, 1]} openAtRest followedByText>
        <div>chain</div>
      </WorkChain>,
    );
    expect(headerText(done.container)).toBe("Worked");
  });

  it("falls back to the plain title when it has no indices to describe", () => {
    aui.parts = [doneTool("digisearch"), answer];
    const { container } = render(
      <WorkChain followedByText>
        <div>chain</div>
      </WorkChain>,
    );
    expect(headerText(container)).toBe("Worked");
  });

  it("names the chain trigger by its title only (DIG-4669)", () => {
    aui.parts = [doneTool("digisearch"), answer];
    render(
      <WorkChain indices={[0, 1]} followedByText>
        <div>chain</div>
      </WorkChain>,
    );
    // The marker used to carry the same title as the label, so the trigger
    // announced the title twice.
    const trigger = screen.getByRole("button", { name: "Used 1 tool" });
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });
});

describe("WorkChain header after the turn ends early", () => {
  it.each([
    [{ type: "incomplete", reason: "error" }, "Failed", "error"],
    [{ type: "incomplete", reason: "cancelled" }, "Stopped", "stop"],
    [{ type: "requires-action", reason: "tool-calls" }, "Stopped", "stop"],
  ])("status %j reads %s with a still %s marker", (status, title, marker) => {
    aui.parts = [runningReasoning, runningTool("digisearch")] as unknown as WorkStatusPart[];
    aui.status = status;
    const { container } = render(
      <WorkChain indices={[0, 1]}>
        <div />
      </WorkChain>,
    );
    expect(headerText(container)).toBe(title);
    expect(
      container
        .querySelector('[data-slot="aui_work-status-marker"] [data-slot="dot-matrix"]')
        ?.getAttribute("data-state"),
    ).toBe(marker);
    expect(container.querySelector('[data-slot="aui_work-chain"]')?.getAttribute("data-outcome")).toBe(
      status.reason === "error" ? "failed" : "stopped",
    );
  });

  it("a stop after the answer started still reads Worked", () => {
    aui.parts = [doneTool("digisearch"), answer] as unknown as WorkStatusPart[];
    aui.status = { type: "incomplete", reason: "cancelled" };
    const { container } = render(
      <WorkChain indices={[0]} followedByText>
        <div />
      </WorkChain>,
    );
    expect(container.querySelector('[data-slot="aui_work-chain"]')?.getAttribute("data-outcome")).toBe("done");
  });
});
