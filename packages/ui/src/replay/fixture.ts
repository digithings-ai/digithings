/**
 * A finished demo conversation with no credentials. Tests and the sample
 * export both build from this, so the artifact matches what the suite renders.
 */

import { messagesToReplay, type ReplayChromeInput } from "./from-messages";
import type { ReplayDocument } from "./types";

export const FIXTURE_EXPORTED_AT = "2026-10-21T15:04:00.000Z";

export function fixtureChrome(): ReplayChromeInput {
  return {
    deployment: "northwind",
    title: "Northwind",
    welcome: "Northwind desk",
    welcomeBody: ["A finished conversation, saved for the demo."],
    suggestions: ["What moved in the book?", "Walk through the copper hedge"],
    placeholder: "Message Northwind",
    accent: { color: "#c4f24a", foreground: "#10140c" }, // canon-allow: sample tenant accent for the offline fixture, not a UI style
    theme: {
      preference: "dark",
      resolved: "dark",
      palette: "default",
      view: "balanced",
    },
  };
}

export const fixtureMessages: readonly unknown[] = [
  {
    id: "u1",
    role: "user",
    parts: [{ type: "text", text: "What moved in the book overnight?" }],
  },
  {
    id: "a1",
    role: "assistant",
    parts: [
      {
        type: "reasoning",
        text: "The book is the positions we already hold. I'll read the close recap, then the fills.",
      },
      {
        type: "tool-digisearch",
        toolCallId: "call-search",
        state: "output-available",
        input: { query: "overnight book changes", collection: "research" },
        output: {
          notes: [
            {
              title: "Close recap",
              excerpt: "Copper hedge was lifted. The equity sleeve is unchanged.",
            },
          ],
        },
      },
      {
        type: "text",
        text: [
          "Overnight the book did two things.",
          "",
          "## Close recap",
          "",
          "- Copper hedge was **lifted**",
          "- Equity sleeve is unchanged",
          "",
          "```",
          "sleeve   status",
          "copper   flat",
          "equity   held",
          "```",
        ].join("\n"),
      },
    ],
  },
  {
    id: "u2",
    role: "user",
    parts: [{ type: "text", text: "Walk through the copper hedge." }],
  },
  {
    id: "a2",
    role: "assistant",
    parts: [
      {
        type: "data-notice",
        data: {
          tone: "status",
          message: "Source is the research corpus, not a live broker.",
          detail: "No orders were sent.",
        },
      },
      {
        type: "text",
        text: "The hedge was a short copper future against the long physical. Lifting it leaves the physical unhedged into the open.",
      },
    ],
  },
];

export function fixtureDocument(): ReplayDocument {
  return messagesToReplay(fixtureMessages, fixtureChrome(), FIXTURE_EXPORTED_AT);
}
