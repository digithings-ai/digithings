/**
 * Renders the agent chain and asserts the canon primitives actually reach the
 * markup — the regression this suite exists for is the embed silently showing
 * no tool chain / no reasoning (#1418 gap 6).
 *
 * Asserted against SERVER-rendered output on purpose. Tool heads and meta
 * counts land in the first paint; hit lists stay folded on the tool row
 * (Claude Code grammar) and mount only on expand.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatActivities } from "./ChatActivities";
import type { DigiChatActivity } from "../types";

const render = (activities: DigiChatActivity[]) =>
  renderToStaticMarkup(<ChatActivities activities={activities} />);

describe("ChatActivities — tool calls render in the canon grammar", () => {
  it("renders an in-flight tool call as a running ChatToolCall row", () => {
    const html = render([{ kind: "tool_call", name: "digivault.search", query: "how auth works" }]);

    // The shared primitive's own structure — not a re-implementation.
    expect(html).toContain('class="tc');
    expect(html).toContain("tc-head");
    expect(html).toContain("digivault.search");
    expect(html).toContain("how auth works");
    // Running status wears the pulsing ellipsis, not a tick.
    expect(html).toContain("tc-run");
    expect(html).toContain("…");
    // Searching… is a real body so the head is a disclosure with a caret.
    expect(html).toContain("Searching…");
    expect(html).toContain("aria-expanded");
    expect(html).toContain("tc-caret");
  });

  it("renders a completed tool call as an expandable block with its outcome count", () => {
    const html = render([
      {
        kind: "tool_result",
        name: "digivault.search",
        query: "auth",
        count: 2,
        hits: [
          { title: "Auth overview", path: "docs/auth.md" },
          { title: "JWT exchange", path: "docs/jwt.md" },
        ],
      },
    ]);

    expect(html).toContain("digivault.search");
    expect(html).toContain("✓");
    expect(html).toContain("2 notes");
    // Hits fold under the tool — closed by default.
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("docs/auth.md");
  });

  it("renders a failed-search aside rather than a fake empty result", () => {
    const html = render([{ kind: "status", message: 'Search for "auth" failed.' }]);
    // Canon system aside: the `·` marker row.
    expect(html).toContain("chat-msg--system");
    expect(html).toContain("·");
    expect(html).toContain("Search for &quot;auth&quot; failed.");
  });

  it("renders an opaque upstream step as a bodyless tool row", () => {
    const html = render([{ kind: "trace", label: "Searching the vault", done: true }]);
    expect(html).toContain("Searching the vault");
    expect(html).toContain("✓");
    expect(html).not.toContain("aria-expanded");
  });
});

describe("ChatActivities — reasoning renders as a disclosure", () => {
  it("puts the reasoning chain behind a ChatThinking chip", () => {
    const html = render([
      { kind: "reasoning", text: "First check the vault.\nThen compare both answers." },
    ]);

    // The shared ChatThinking chip, collapsed by default.
    expect(html).toContain("think-chip");
    expect(html).toContain("think-caret");
    expect(html).toContain("think-dot");
    expect(html).toContain("reasoning");
    expect(html).toContain('aria-expanded="false"');
  });

  it("keeps the reasoning text out of the collapsed markup", () => {
    const html = render([{ kind: "reasoning", text: "SECRET-CHAIN-OF-THOUGHT" }]);
    // Folded by default — the body mounts on expand, so a long chain never
    // dominates the transcript.
    expect(html).not.toContain("SECRET-CHAIN-OF-THOUGHT");
  });
});

describe("ChatActivities — sources render as citations", () => {
  it("folds retrieved documents behind the tool disclosure (body mounts on expand)", () => {
    const html = render([
      {
        kind: "tool_result",
        name: "digivault.search",
        query: "auth",
        count: 2,
        hits: [
          {
            title: "Auth overview",
            path: "docs/auth.md",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "RS256 token exchange…",
          },
          { title: "JWT exchange", path: "docs/jwt.md" },
        ],
      },
    ]);

    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain("2 notes");
    expect(html).not.toContain("dc-act-hits");
    expect(html).not.toContain("docs/auth.md");
    expect(html).not.toContain("RS256 token exchange…");
  });

  it("says so plainly when a search found nothing", () => {
    const html = render([
      { kind: "tool_result", name: "digivault.search", query: "nothing", count: 0, hits: [] },
    ]);
    expect(html).toContain("no hits");
    expect(html).not.toContain("dc-act-hits");
  });

  it("renders a research brief as a titled card", () => {
    const html = render([
      {
        kind: "brief",
        themes: [{ label: "Auth", summary: "RS256 tokens" }],
        questions: ["Which tenant?"],
      },
    ]);
    expect(html).toContain("research brief");
    expect(html).toContain("Auth");
    expect(html).toContain("RS256 tokens");
    expect(html).toContain("Next questions");
    expect(html).toContain("Which tenant?");
  });
});

describe("ChatActivities — the chain as a whole", () => {
  it("renders a full mixed turn in order, labelled for assistive tech", () => {
    const html = render([
      { kind: "trace", label: "Planning", done: true },
      { kind: "tool_call", name: "digivault.search", query: "auth" },
      {
        kind: "tool_result",
        name: "digivault.search",
        query: "auth",
        count: 1,
        hits: [{ title: "Auth", path: "docs/auth.md" }],
      },
      { kind: "reasoning", text: "weighing the docs" },
    ]);

    expect(html).toContain('aria-label="Agent steps"');
    // Order of heads: Planning → running search → settled search (folded) → reasoning.
    expect(html.indexOf("Planning")).toBeLessThan(html.indexOf("tc-run"));
    expect(html.indexOf("1 note")).toBeLessThan(html.indexOf("think-chip"));
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("docs/auth.md");
  });

  it("renders nothing at all for an empty or absent chain", () => {
    expect(render([])).toBe("");
    expect(renderToStaticMarkup(<ChatActivities />)).toBe("");
  });
});
