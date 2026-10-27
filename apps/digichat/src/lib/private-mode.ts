/**
 * Private demo mode: the client sends `x-digi-private: 1` when the transcript
 * may be shown to the party it is about, and every turn carries an instruction
 * telling the model to substitute the real names and identifiers it is given.
 *
 * The stand-in rosters live here so the wording and the names change in one
 * place; the instruction interpolates them, so it reads exactly as written.
 */

import type { ModelMessage } from "ai";

export const PERSON_STANDINS = [
  "Alex Morgan",
  "Sam Rivera",
  "Jordan Blake",
  "Casey Lindholm",
  "Robin Hale",
  "Dana Whitfield",
] as const;

export const ORG_STANDINS = [
  "Northwind Trading",
  "Blue Harbor Group",
  "Meridian Partners",
  "Cedar Lane Systems",
] as const;

export const PRIVATE_MODE_INSTRUCTION = `PRIVATE DEMO SESSION. This transcript may be shown to the client. Replace every real person name, organisation name, email address, phone number, street address, ticket id, and invoice or contract number belonging to a real party with a fictional stand-in, and use the stand-in instead of the original in all of your output.
Assign stand-ins in the order parties first appear and reuse each one for the rest of the conversation: ${PERSON_STANDINS.join(", ")} for people; ${ORG_STANDINS.join(", ")} for organisations. When those run out use Person_N, Org_N, Ticket_N and keep counting upward.
Never renumber a stand-in and never give two different parties the same one. Treat all surface forms of one party as that party: "John Smith", "John", "J. Smith" and "jsmith@acme.com" are the same party and take one stand-in.
Never state that you are substituting, and never repeat an original value.`;

/** True only for an exact `x-digi-private: 1`. */
export function isPrivateMode(headers: Headers): boolean {
  return (headers.get("x-digi-private") || "").trim() === "1";
}

/**
 * Append the private-mode instruction to the **last user turn**.
 *
 * It cannot ride a `system` message or an AI SDK `instructions` option: the
 * digigraph backend flattens the request into a single prompt and drops every
 * turn that is not `user` or `assistant` (`digigraph/chat_prompt.py`, pinned by
 * `test_system_messages_are_omitted`), and its request model forbids an
 * `instructions` field outright. A user turn is the only channel that reaches
 * the model, so the policy text goes there. Do not "tidy" this back into a
 * system message — it would be silently discarded and private mode would look
 * like it works while doing nothing.
 *
 * Only the last user turn is touched, so earlier turns keep their original
 * text, and the mutation happens on the converted model messages: what the
 * client stores and renders is unchanged.
 */
export function withPrivateModePrompt(messages: ModelMessage[]): ModelMessage[] {
  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") {
      lastUserIndex = index;
      break;
    }
  }
  if (lastUserIndex === -1) return messages;

  const target = messages[lastUserIndex];
  if (!target || target.role !== "user") return messages;

  const content = target.content;
  const patched: ModelMessage =
    typeof content === "string"
      ? { ...target, content: `${content}\n\n${PRIVATE_MODE_INSTRUCTION}` }
      : {
          ...target,
          content: [
            ...content,
            { type: "text" as const, text: PRIVATE_MODE_INSTRUCTION },
          ],
        };

  return messages.map((message, index) =>
    index === lastUserIndex ? patched : message,
  );
}
