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
  return (
    process.env.NODE_ENV !== "production" &&
    process.env.DIGICHAT_DEMO_CHAT === "1"
  );
}

/** A canned reply, streamed in the same shape as a real one. */
export function demoChatResponse(): Response {
  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      writer.write({ type: "reasoning-start", id: "demo-reasoning" });
      for (const delta of REASONING) {
        writer.write({ type: "reasoning-delta", id: "demo-reasoning", delta });
        await sleep(220);
      }
      writer.write({ type: "reasoning-end", id: "demo-reasoning" });

      for (const tool of TOOLS) {
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
