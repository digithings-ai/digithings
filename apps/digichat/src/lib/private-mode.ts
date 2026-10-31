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
This applies to everything you are given, including tool results, ticket contents, requester and agent names, and help documentation.
You are a generic support assistant for a help desk. Never name the product, platform, ticketing system or organisation this service belongs to, including any name that appears in a tool result or a document; call it "the help desk" or "the support team" instead.
Never state that you are substituting, and never repeat an original value.`;

/** True only for an exact `x-digi-private: 1`. */
export function isPrivateMode(headers: Headers): boolean {
  return (headers.get("x-digi-private") || "").trim() === "1";
}

/**
 * Id of the request-only user message that carries the instruction.
 * Adapters recognise it and keep it out of the typed user text.
 */
export const PRIVATE_MODE_MESSAGE_ID = "digi-private-instruction";

/**
 * Insert the private-mode instruction as its **own user message**, immediately
 * before the last user turn.
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
 * The instruction is its own message, not a part of the typed turn. Digigraph
 * reads the last user turn as the tool query (`last_user_turn`); gluing the
 * instruction onto that text would change what tools search for. A message
 * placed just before the question stays in the model payload and leaves the
 * question byte-identical.
 *
 * Only the request copy changes: what the client stores, re-sends and renders
 * is unchanged.
 */
export function withPrivateModeUiPrompt(messages: UIMessage[]): UIMessage[] {
  if (messages.some((message) => message.id === PRIVATE_MODE_MESSAGE_ID)) {
    return messages;
  }
  let lastUserIndex = -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === "user") {
      lastUserIndex = index;
      break;
    }
  }
  if (lastUserIndex === -1) return messages;

  const instruction: UIMessage = {
    id: PRIVATE_MODE_MESSAGE_ID,
    role: "user",
    parts: [{ type: "text", text: PRIVATE_MODE_INSTRUCTION }],
  };
  return [
    ...messages.slice(0, lastUserIndex),
    instruction,
    ...messages.slice(lastUserIndex),
  ];
}

/** The instruction text when this request copy carries the private message. */
export function privateModeInstructionText(messages: readonly UIMessage[]): string | null {
  const hit = messages.find(
    (message) => message.id === PRIVATE_MODE_MESSAGE_ID && message.role === "user",
  );
  if (!hit) return null;
  const text = hit.parts
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");
  return text === PRIVATE_MODE_INSTRUCTION ? text : null;
}

/**
 * Provider `{role, content}` bodies. A joiner that glues the instruction onto
 * the question is split so the question stays its own message and comes last
 * — that last user turn is what tools search.
 */
export function separatePrivateInstructionPayload<T extends { role: string; content: string }>(
  messages: readonly T[],
): T[] {
  const out: T[] = [];
  for (const message of messages) {
    if (message.role !== "user" || !message.content.includes(PRIVATE_MODE_INSTRUCTION)) {
      out.push(message);
      continue;
    }
    if (message.content.trim() === PRIVATE_MODE_INSTRUCTION) {
      out.push({ ...message, content: PRIVATE_MODE_INSTRUCTION });
      continue;
    }
    const at = message.content.indexOf(PRIVATE_MODE_INSTRUCTION);
    const before = message.content.slice(0, at).trim();
    const after = message.content
      .slice(at + PRIVATE_MODE_INSTRUCTION.length)
      .trim();
    const userText = [before, after].filter(Boolean).join("\n\n");
    out.push({ ...message, content: PRIVATE_MODE_INSTRUCTION });
    if (userText) out.push({ ...message, content: userText });
  }
  return out;
}
