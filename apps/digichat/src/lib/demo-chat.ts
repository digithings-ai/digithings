import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

/**
 * Dev-only canned chat: a reasoning block, three consecutive tool calls and a
 * final answer.
 *
 * The local embed has no model behind it, so without this the tool chain can
 * never be seen: no tool calls, no reasoning, no grouping, no banners. The
 * parts below are the same UI-message-stream chunks the real BFF emits (see
 * `lib/adapters/digithings/stream.ts` and `lib/ui-stream-parts.ts`), so
 * grouping, disclosure and the banner behave exactly as they do in
 * production — only the content is made up.
 *
 * The content is deliberately client-neutral: the R0 gate keeps client names
 * out of the repository, and a demo that named a client would leak one.
 *
 * Enabled by `DIGICHAT_DEMO_CHAT=1` and never in production.
 * `DIGICHAT_DEMO_CHAT=long` streams a longer trace (three reasoning blocks
 * around five tool calls, then a list answer) for density and spacing review.
 */

const REASONING = [
  "The question is about how to raise a support ticket.\n",
  "The help articles are the authoritative source, so I will search them first.\n",
  "Then I will read the internal notes for the same topic, and finish with the live ticket list so the answer can name real tickets.\n",
];

const TEXT = [
  "You raise a ticket from the customer portal: **Service Desk → New ticket**.\n\n",
  "Pick the category that matches — *Access & onboarding* for account questions, *Mail archive* for archive access, or *Data protection* for retention and deletion. ",
  "Add the subject, a short description and the affected mailbox, then submit — you get a ticket number by email within a working day.\n\n",
  "Tickets are handled in the order they arrive; the three most recent open ones right now are #4120 (faulty PDF display), #4131 (two-factor login) and #4147 (mail archive access).\n",
];

const TOOLS: {
  toolCallId: string;
  toolName: string;
  input: unknown;
  output: string;
}[] = [
  {
    toolCallId: "demo-1",
    toolName: "digisearch",
    input: { query: "how to raise a support ticket", index: "help_articles" },
    output:
      "help_articles: 3 documents — “Raising a ticket (Service Desk)”, “Service Desk categories”, “Response times”. Snippet: “Open the portal, choose Service Desk → New ticket, pick a category, add the subject and the affected mailbox, then submit.”",
  },
  {
    toolCallId: "demo-2",
    toolName: "vault_get_note",
    input: {
      vault_paths: [
        "clients/knowledge-base/user-administrator-manual-i004",
        "clients/knowledge-base/user-administrator-manual-i045",
      ],
      query: "6 notes",
    },
    output:
      "6 notes read. “Users raise tickets themselves from the portal; the categories are Access & onboarding, Mail archive, Data protection, Reporting.” “First response within one working day.”",
  },
  {
    toolCallId: "demo-3",
    toolName: "ticketing_list_tickets",
    input: { state: "open", limit: 3 },
    output:
      "#4120 Fehlerhafte Anzeige PDF Dokument (faulty display of PDF document) · #4131 kann mich nicht mehr anmelden / 2FA (cannot log in anymore) · #4147 Benutzer kann auf Mailarchiv nicht zugreifen (user cannot access mail archive)",
  },
];

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** The demo is a development affordance; it must never reach production. */
export function isDemoChatEnabled(): boolean {
  const mode = process.env.DIGICHAT_DEMO_CHAT;
  return process.env.NODE_ENV !== "production" && (mode === "1" || mode === "long");
}

/** The long trace: used to review density and spacing across a full chain. */
export function isLongDemoChat(): boolean {
  return process.env.DIGICHAT_DEMO_CHAT === "long";
}

const LONG_STEPS: (
  | { kind: "reasoning"; id: string; deltas: string[] }
  | { kind: "tool"; toolCallId: string; toolName: string; input: unknown; output: string }
)[] = [
  { kind: "reasoning", id: "long-r1", deltas: [REASONING[0], REASONING[1]] },
  { kind: "tool", ...TOOLS[0] },
  { kind: "tool", ...TOOLS[1] },
  {
    kind: "reasoning",
    id: "long-r2",
    deltas: [
      "The articles and the notes agree on the categories.\n",
      "I still need the response times and the live ticket list before I answer.\n",
    ],
  },
  {
    kind: "tool",
    toolCallId: "long-4",
    toolName: "digisearch",
    input: { query: "service desk response times", index: "help_articles" },
    output: "help_articles: 1 document — “Response times”. Snippet: “First response within one working day; urgent access issues within four hours.”",
  },
  { kind: "tool", ...TOOLS[2] },
  {
    kind: "tool",
    toolCallId: "long-5",
    toolName: "ticketing_get_ticket",
    input: { id: 4147 },
    output: "#4147 · state open · category Mail archive · opened 2 days ago · last update today",
  },
  { kind: "reasoning", id: "long-r3", deltas: [REASONING[2]] },
];

const LONG_TEXT = [
  "You raise a ticket from the customer portal.\n\n",
  "1. Open **Service Desk → New ticket**.\n",
  "2. Pick the category: *Access & onboarding*, *Mail archive* or *Data protection*.\n",
  "3. Add the subject, a short description and the affected mailbox, then submit.\n\n",
  "- First response within one working day.\n",
  "- Urgent access issues within four hours.\n\n",
  "The three most recent open tickets are #4120, #4131 and #4147.\n",
];

function longDemoChatResponse(): Response {
  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      for (const step of LONG_STEPS) {
        if (step.kind === "reasoning") {
          writer.write({ type: "reasoning-start", id: step.id });
          for (const delta of step.deltas) {
            writer.write({ type: "reasoning-delta", id: step.id, delta });
            await sleep(120);
          }
          writer.write({ type: "reasoning-end", id: step.id });
          continue;
        }
        writer.write({ type: "tool-input-start", toolCallId: step.toolCallId, toolName: step.toolName });
        writer.write({
          type: "tool-input-delta",
          toolCallId: step.toolCallId,
          inputTextDelta: JSON.stringify(step.input),
        });
        writer.write({
          type: "tool-input-available",
          toolCallId: step.toolCallId,
          toolName: step.toolName,
          input: step.input,
        });
        await sleep(160);
        writer.write({ type: "tool-output-available", toolCallId: step.toolCallId, output: step.output });
        await sleep(80);
      }
      writer.write({ type: "text-start", id: "long-text" });
      for (const delta of LONG_TEXT) {
        writer.write({ type: "text-delta", id: "long-text", delta });
        await sleep(60);
      }
      writer.write({ type: "text-end", id: "long-text" });
    },
  });
  return createUIMessageStreamResponse({ stream });
}

/** A canned reply, streamed in the same shape as a real one. */
export function demoChatResponse(): Response {
  if (isLongDemoChat()) return longDemoChatResponse();
  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      writer.write({ type: "reasoning-start", id: "demo-reasoning" });
      for (const delta of REASONING) {
        writer.write({ type: "reasoning-delta", id: "demo-reasoning", delta });
        await sleep(220);
      }
      writer.write({ type: "reasoning-end", id: "demo-reasoning" });

      for (const [index, tool] of TOOLS.entries()) {
        // A status part between two tool runs: the work continues, so it
        // belongs to the same work block (this is what the real digigraph
        // stream emits between a retrieve and the next call).
        if (index === 2) {
          writer.write({
            type: "data-status",
            data: { status: "working", step: "now reading the notes" },
          });
        }
        writer.write({
          type: "tool-input-start",
          toolCallId: tool.toolCallId,
          toolName: tool.toolName,
        });
        writer.write({
          type: "tool-input-delta",
          toolCallId: tool.toolCallId,
          inputTextDelta: JSON.stringify(tool.input),
        });
        writer.write({
          type: "tool-input-available",
          toolCallId: tool.toolCallId,
          toolName: tool.toolName,
          input: tool.input,
        });
        await sleep(320);
        writer.write({
          type: "tool-output-available",
          toolCallId: tool.toolCallId,
          output: tool.output,
        });
        await sleep(180);
      }

      writer.write({ type: "text-start", id: "demo-text" });
      for (const delta of TEXT) {
        writer.write({ type: "text-delta", id: "demo-text", delta });
        await sleep(90);
      }
      writer.write({ type: "text-end", id: "demo-text" });
    },
  });
  return createUIMessageStreamResponse({ stream });
}
