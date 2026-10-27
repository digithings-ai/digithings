/**
 * Private demo mode: the client sends `x-digi-private: 1` when the transcript
 * may be shown to the party it is about, and every turn carries an instruction
 * telling the model to substitute the real names and identifiers it is given.
 *
 * The stand-in rosters live here so the wording and the names change in one
 * place; the instruction interpolates them, so it reads exactly as written.
 */

import type { UIMessage } from "ai";

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
 * Append the private-mode instruction to the **last user turn's parts**.
 *
 * Two constraints decide the shape of this:
 *
 * 1. It cannot ride a `system` message. Digigraph flattens the request into a
 *    single prompt and drops every turn that is not `user` or `assistant`
 *    (`digigraph/chat_prompt.py`, pinned by `test_system_messages_are_omitted`),
 *    and its request model forbids an `instructions` field outright.
 * 2. It has to be applied to the **UI messages**, before the route picks a
 *    backend adapter. `api/chat/route.ts` has five paths (foundry, the two
 *    non-AI-SDK and AI-SDK branches, the digigraph trace stream, and the legacy
 *    `streamText` pair) and the trace stream is the default one. Patching the
 *    converted model messages reaches only the legacy pair, which is how this
 *    first shipped as a no-op. Every path consumes `messages`, so that is where
 *    the instruction goes.
 *
 * Only the last user turn is touched, and only in the request copy: what the
 * client stores, re-sends and renders is unchanged.
 */
export function withPrivateModeUiPrompt(messages: UIMessage[]): UIMessage[] {
  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") {
      lastUserIndex = index;
      break;
    }
  }
  if (lastUserIndex === -1) return messages;

  const target = messages[lastUserIndex];
  if (!target) return messages;

  const patched: UIMessage = {
    ...target,
    parts: [...target.parts, { type: "text", text: PRIVATE_MODE_INSTRUCTION }],
  };

  return messages.map((message, index) =>
    index === lastUserIndex ? patched : message,
  );
}
