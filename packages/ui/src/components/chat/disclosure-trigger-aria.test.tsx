// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

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
 * DIG-4669: a disclosure trigger is named by its visible text, once.
 *
 * PR #6034 replaced the nameless lucide glyphs in the chat triggers with
 * DotMatrix instances that carry a label, and DotMatrix renders that label as
 * the accessible name of a `role="img"` element. Name-from-content then reads
 * the icon's name and the control's own visible text, so the trigger
 * announced "Reasoning Reasoning (5s) Toggle reasoning" - the label twice,
 * plus a chevron name the button never needed.
 *
 * The rule these tests pin: the visible text is the name of the control, and
 * every glyph inside it is decorative.
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
    expect(trigger).toBeTruthy();
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
    expect(trigger).toBeTruthy();
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
    expect(trigger).toBeTruthy();
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("names the running tool group trigger by its count only", () => {
    render(
      <ToolGroupRoot>
        <ToolGroupTrigger count={1} active />
        <ToolGroupContent>the calls</ToolGroupContent>
      </ToolGroupRoot>,
    );

    const trigger = screen.getByRole("button", { name: "1 tool call" });
    expect(trigger).toBeTruthy();
    expect(trigger.querySelector('[role="img"]')).toBeNull();
  });

  it("names the tool fallback trigger by its visible text only", () => {
    render(
      <ToolFallbackRoot>
        <ToolFallbackTrigger toolName="digisearch" title="digisearch" />
        <ToolFallbackContent>the result</ToolFallbackContent>
      </ToolFallbackRoot>,
    );

    const trigger = screen.getByRole("button", { name: "Used tool: digisearch" });
    expect(trigger).toBeTruthy();
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
});
