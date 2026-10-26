// @vitest-environment happy-dom
"use client";

/**
 * Starter-chip cap and cycle.
 *
 * The welcome used to print every starter a tenant defines (the house tenant
 * defines eight, the trial five) — a wall of prompts. Four is the whole row; the rest is
 * reached by cycling, which never starts under reduced motion, holds while the
 * row is hovered or focused, and stops for good once the conversation has
 * started or the composer holds text.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  SUGGESTION_CYCLE_MS,
  VISIBLE_SUGGESTIONS,
  suggestionWindow,
  useSuggestionCycle,
  useThreadActivity,
} from "@digithings/ui/chat/suggestions";

const EIGHT = [
  "What does digigraph orchestrate?",
  "How do I run a backtest?",
  "Which models are available?",
  "What is in the knowledge base?",
  "How does digikey issue a token?",
  "Show me the MCP tool catalog",
  "What did the last release ship?",
  "How do I deploy the stack?",
];

type ThreadCore = {
  messages: readonly unknown[];
};

/** A stand-in for the assistant-ui runtime the product shell owns. */
function fakeRuntime(core: ThreadCore, composer = { text: "" }) {
  const listeners = new Set<() => void>();
  return {
    thread: {
      getState: () => core,
      composer: { getState: () => composer },
      subscribe: (callback: () => void) => {
        listeners.add(callback);
        return () => listeners.delete(callback);
      },
      push: () => listeners.forEach((callback) => callback()),
    },
  };
}

/** The product shell's exact wiring: activity drives `stopped`. */
function Harness({
  all,
  runtime,
}: {
  all: readonly string[];
  runtime: { thread?: unknown };
}) {
  const activity = useThreadActivity(runtime);
  const cycle = useSuggestionCycle(all, {
    stopped: activity.started || activity.typed,
  });
  return (
    <div {...cycle.handlers}>
      <div data-testid="group" data-offset={cycle.offset}>
        {cycle.visible.map((prompt) => (
          <button key={prompt} type="button">
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

function shown(): string[] {
  return screen.getAllByRole("button").map((node) => node.textContent ?? "");
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("suggestionWindow", () => {
  it("caps to the visible count and wraps through the whole list", () => {
    expect(suggestionWindow(EIGHT, 0)).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
    expect(suggestionWindow(EIGHT, VISIBLE_SUGGESTIONS)).toEqual(
      EIGHT.slice(VISIBLE_SUGGESTIONS),
    );
    // Past the end it wraps rather than going blank.
    expect(suggestionWindow(EIGHT, 8)).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
    // A short list is never padded.
    expect(suggestionWindow(["one", "two"], 0)).toEqual(["one", "two"]);
  });
});

describe("starter chips", () => {
  it("renders four of eight defined suggestions, not all eight", () => {
    const runtime = fakeRuntime({ messages: [] });
    render(<Harness all={EIGHT} runtime={runtime} />);
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
    expect(screen.getAllByRole("button")).toHaveLength(4);
  });

  it("cycles to the next group after the interval, keeping four on screen", () => {
    vi.useFakeTimers();
    const runtime = fakeRuntime({ messages: [] });
    render(<Harness all={EIGHT} runtime={runtime} />);

    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS - 1);
    });
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(shown()).toEqual(EIGHT.slice(VISIBLE_SUGGESTIONS));
    expect(screen.getAllByRole("button")).toHaveLength(4);

    // Wraps back to the first group, so every starter is seen.
    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS);
    });
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
  });

  it("pauses while the pointer is over the chips and resumes after", () => {
    vi.useFakeTimers();
    const runtime = fakeRuntime({ messages: [] });
    render(<Harness all={EIGHT} runtime={runtime} />);
    const row = screen.getByTestId("group").parentElement!;

    fireEvent.pointerEnter(row);
    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS * 3);
    });
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));

    fireEvent.pointerLeave(row);
    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS);
    });
    expect(shown()).toEqual(EIGHT.slice(VISIBLE_SUGGESTIONS));
  });

  it("pauses while focus is inside the chips", () => {
    vi.useFakeTimers();
    const runtime = fakeRuntime({ messages: [] });
    render(<Harness all={EIGHT} runtime={runtime} />);
    const row = screen.getByTestId("group").parentElement!;

    fireEvent.focusIn(row);
    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS * 2);
    });
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));

    fireEvent.focusOut(row);
    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS);
    });
    expect(shown()).toEqual(EIGHT.slice(VISIBLE_SUGGESTIONS));
  });

  it("stops once the thread has messages", () => {
    vi.useFakeTimers();
    const core: ThreadCore = { messages: [] };
    const runtime = fakeRuntime(core);
    render(<Harness all={EIGHT} runtime={runtime} />);

    core.messages = [{ id: "m1" }];
    act(() => {
      runtime.thread.push();
    });

    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS * 3);
    });
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
  });

  it("stops once the visitor has typed a draft", () => {
    vi.useFakeTimers();
    const composer = { text: "" };
    const runtime = fakeRuntime({ messages: [] }, composer);
    render(<Harness all={EIGHT} runtime={runtime} />);

    composer.text = "half a question";
    act(() => {
      runtime.thread.push();
    });

    act(() => {
      vi.advanceTimersByTime(SUGGESTION_CYCLE_MS * 3);
    });
    expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
  });

  it("never cycles under prefers-reduced-motion: the first four only", () => {
    vi.useFakeTimers();
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      const runtime = fakeRuntime({ messages: [] });
      render(<Harness all={EIGHT} runtime={runtime} />);
      act(() => {
        vi.advanceTimersByTime(SUGGESTION_CYCLE_MS * 4);
      });
      expect(shown()).toEqual(EIGHT.slice(0, VISIBLE_SUGGESTIONS));
    } finally {
      window.matchMedia = original;
    }
  });
});

describe("useThreadActivity", () => {
  it("reports started and typed from the runtime, and survives a bare runtime", async () => {
    // An SSR pass or a test double with no thread reports the empty state.
    function Probe({ runtime }: { runtime: { thread?: unknown } }) {
      const activity = useThreadActivity(runtime);
      return (
        <span data-testid="activity">{`${activity.started}:${activity.typed}`}</span>
      );
    }
    render(<Probe runtime={{}} />);
    // The first read is deferred out of the effect body (react-hooks rule).
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("activity").textContent).toBe("false:false");
    cleanup();

    const runtime = fakeRuntime({ messages: [{ id: "m1" }] }, { text: "hey" });
    render(<Probe runtime={runtime} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId("activity").textContent).toBe("true:true");
  });
});
