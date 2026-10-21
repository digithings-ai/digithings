// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DotMatrix } from "./DotMatrix";
import {
  ReasoningContent as GalleryReasoningContent,
  ReasoningRoot as GalleryReasoningRoot,
  ReasoningTrigger as GalleryReasoningTrigger,
} from "./gallery-thread/reasoning";
import {
  ReasoningContent,
  ReasoningRoot,
  ReasoningTrigger,
} from "./stock/reasoning";
import {
  ToolFallbackContent,
  ToolFallbackRoot,
  ToolFallbackTrigger,
} from "./stock/tool-fallback.aui";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "./stock/tool-group.aui";

/**
 * DIG-4669: a control is named by its visible text, once.
 *
 * PR #6034 replaced the nameless lucide glyphs in the chat triggers with
 * DotMatrix instances that carry a label, and DotMatrix renders that label as
 * the accessible name of a `role="img"` element. Name-from-content then reads
 * the icon's name and the control's own visible text, so the trigger
 * announced "Reasoning Reasoning (5s) Toggle reasoning" - the label twice,
 * plus a chevron name the button never needed.
 *
 * The rule these tests pin: a control that has visible text is named by that
 * text, and every glyph inside it is decorative. A control with no visible
 * text is named by its glyph.
 */

afterEach(cleanup);

describe("disclosure trigger accessible names", () => {
  it("names the reasoning trigger by its visible text only", () => {
    render(
      <ReasoningRoot>
        <ReasoningTrigger duration={5} />
        <ReasoningContent>the thinking</ReasoningContent>
      </ReasoningRoot>,
    );

    const trigger = screen.getByRole("button", { name: "Reasoning (5s)" });
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("names the gallery reasoning trigger by its visible text only", () => {
    render(
      <GalleryReasoningRoot>
        <GalleryReasoningTrigger duration={5} />
        <GalleryReasoningContent>the thinking</GalleryReasoningContent>
      </GalleryReasoningRoot>,
    );

    const trigger = screen.getByRole("button", { name: "Reasoning (5s)" });
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("names the tool group trigger by its count only", () => {
    render(
      <ToolGroupRoot>
        <ToolGroupTrigger count={3} />
        <ToolGroupContent>the calls</ToolGroupContent>
      </ToolGroupRoot>,
    );

    const trigger = screen.getByRole("button", { name: "3 tool calls" });
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("keeps the running state of the tool group on the trigger, not in a second name", () => {
    render(
      <ToolGroupRoot>
        <ToolGroupTrigger count={1} active />
        <ToolGroupContent>the calls</ToolGroupContent>
      </ToolGroupRoot>,
    );

    // The group is collapsed while the tools run, so the trigger is the only
    // thing on screen that knows about it: the state has to be on it.
    const trigger = screen.getByRole("button", { name: "1 tool call" });
    expect(trigger.getAttribute("aria-busy")).toBe("true");
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("leaves a finished tool group not busy", () => {
    render(
      <ToolGroupRoot>
        <ToolGroupTrigger count={1} />
        <ToolGroupContent>the calls</ToolGroupContent>
      </ToolGroupRoot>,
    );

    const trigger = screen.getByRole("button", { name: "1 tool call" });
    expect(trigger.getAttribute("aria-busy")).toBeNull();
  });

  it("names the tool fallback trigger by its visible text only", () => {
    render(
      <ToolFallbackRoot>
        <ToolFallbackTrigger toolName="digisearch" title="digisearch" />
        <ToolFallbackContent>the result</ToolFallbackContent>
      </ToolFallbackRoot>,
    );

    const trigger = screen.getByRole("button", { name: "Used tool: digisearch" });
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("names the running tool fallback trigger by its visible text only", () => {
    render(
      <ToolFallbackRoot>
        <ToolFallbackTrigger
          toolName="digisearch"
          title="digisearch"
          status={{ type: "running" }}
        />
        <ToolFallbackContent>the result</ToolFallbackContent>
      </ToolFallbackRoot>,
    );

    const trigger = screen.getByRole("button", { name: "Running tool: digisearch" });
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("keeps the disclosure state on the trigger", () => {
    render(
      <ReasoningRoot>
        <ReasoningTrigger duration={5} />
        <ReasoningContent>the thinking</ReasoningContent>
      </ReasoningRoot>,
    );

    const trigger = screen.getByRole("button", { name: "Reasoning (5s)" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  it("still names a control that has no visible text by its glyph", () => {
    render(
      <button type="button">
        <DotMatrix state="download" label="Download" />
      </button>,
    );

    // The other half of the rule: a glyph that is the only content of a
    // control is the name of that control.
    screen.getByRole("button", { name: "Download" });
  });
});
