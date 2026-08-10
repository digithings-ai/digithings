/**
 * SSR tests for <TerminalStepCaret> and the two loaders built on it.
 *
 * The caret types imperatively, so the server pass is deliberately thin — an
 * empty label node plus the <noscript> fallback. What IS server-rendered and
 * does matter is the accessibility contract: which class hides the status line
 * and what that line says. Both were defects found in review.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TerminalStepCaret } from "./TerminalStepCaret";
import { ContainerBootLoader, CONTAINER_BOOT_STEPS } from "./ContainerBootLoader";
import { ChatResponseLoader, CHAT_RESPONSE_STEPS } from "./ChatResponseLoader";

const STEPS = ["thinking", "routing through digigraph"];

describe("TerminalStepCaret — server pass", () => {
  it("renders the frame, an empty typed label and the noscript fallback", () => {
    const html = renderToStaticMarkup(<TerminalStepCaret steps={STEPS} />);
    expect(html).toContain("tl-line");
    expect(html).toContain("tl-label");
    // Typed imperatively: the first paint must be the START of the type-out,
    // not a frame of finished text that then clears. So the live label node is
    // served EMPTY — only the <noscript> twin carries text.
    expect(html).toContain('<span class="tl-label" aria-hidden="true"></span>');
    expect(html).toContain("<noscript>");
    expect(html).toContain("thinking");
  });

  it("renders the mark only when one is given", () => {
    expect(renderToStaticMarkup(<TerminalStepCaret steps={STEPS} />)).not.toContain("tl-mark");
    expect(
      renderToStaticMarkup(<TerminalStepCaret steps={STEPS} mark="❯" />),
    ).toContain("tl-mark");
  });
});

// Regression: the status line used Tailwind's `.sr-only`, which is only emitted
// into an app whose own source uses that class. digithings.ai's does not, so
// the "hidden" span rendered as ordinary visible text — a second copy of the
// word beside the one being typed. A shared component's a11y cannot depend on
// the consumer's build config, so the rule ships in terminal-loaders.css.
describe("the screen-reader line", () => {
  /** Just the announced text — the <noscript> fallback also holds a step name. */
  const announced = (html: string) =>
    html.match(/<span class="tl-sr" role="status">([^<]*)</)?.[1];

  it("uses the component's own class, never the Tailwind utility", () => {
    const html = renderToStaticMarkup(<TerminalStepCaret steps={STEPS} />);
    expect(html).toContain('class="tl-sr"');
    expect(html).not.toContain("sr-only");
  });

  // Regression: role="status" is aria-live=polite and its text was the step
  // label, which changes forever while the caret cycles its own script. That
  // recited four invented phrases at a screen reader for the whole wait.
  it("announces a single static line while the steps are the internal script", () => {
    expect(announced(renderToStaticMarkup(<TerminalStepCaret steps={STEPS} />))).toBe("Working…");
  });

  it("announces the real step once a caller drives it — that IS progress", () => {
    const html = renderToStaticMarkup(<TerminalStepCaret steps={STEPS} activeIndex={1} />);
    expect(announced(html)).toBe("routing through digigraph");
  });

  it("lets the caller name the waiting line", () => {
    const html = renderToStaticMarkup(
      <TerminalStepCaret steps={STEPS} waitingLabel="Loading results" />,
    );
    expect(announced(html)).toBe("Loading results");
  });
});

// Regression: `setOwnIndex(i => (i + 1) % 0)` is NaN, and NaN is absorbing —
// steps[NaN] is undefined forever, and since Object.is(NaN, NaN) React bails
// out of both the state update and the effect, so the caret could never
// recover even once real steps arrived.
describe("degenerate input", () => {
  it("renders empty steps without crashing", () => {
    const html = renderToStaticMarkup(<TerminalStepCaret steps={[]} />);
    expect(html).toContain("tl-line");
    expect(html).toContain("tl-label");
  });

  it("wraps an out-of-range or negative activeIndex instead of reading undefined", () => {
    expect(renderToStaticMarkup(<TerminalStepCaret steps={STEPS} activeIndex={5} />)).toContain(
      "routing through digigraph",
    );
    expect(renderToStaticMarkup(<TerminalStepCaret steps={STEPS} activeIndex={-1} />)).toContain(
      "routing through digigraph",
    );
  });
});

describe("the two loaders", () => {
  it("boots into the full-surface frame, holding on the last phase", () => {
    const html = renderToStaticMarkup(<ContainerBootLoader title="digichat" />);
    expect(html).toContain("tl-boot");
    expect(html).toContain("tl-boot-title");
    expect(html).toContain("tl-note");
    expect(html).toContain(CONTAINER_BOOT_STEPS[0]);
  });

  it("drops the note and title when asked", () => {
    const html = renderToStaticMarkup(<ContainerBootLoader note={null} />);
    expect(html).not.toContain("tl-note");
    expect(html).not.toContain("tl-boot-title");
  });

  it("pins to the viewport only when fullscreen", () => {
    expect(renderToStaticMarkup(<ContainerBootLoader fullscreen />)).toContain("is-fixed");
    expect(renderToStaticMarkup(<ContainerBootLoader />)).not.toContain("is-fixed");
  });

  it("puts the response loader in an assistant turn so nothing shifts on swap", () => {
    const html = renderToStaticMarkup(<ChatResponseLoader />);
    expect(html).toContain("tl-line");
    expect(html).toContain(CHAT_RESPONSE_STEPS[0]);
    // <ChatMessage role="assistant"> brings the transcript's own ▸ marker.
    expect(html).toContain("▸");
  });
});
