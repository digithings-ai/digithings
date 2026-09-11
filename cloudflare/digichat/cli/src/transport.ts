/**
 * Official AI SDK v7 transport for the Ink process.
 * Absolute URL required — the terminal has no browser origin.
 * https://www.assistant-ui.com/docs/ink/custom-backend
 */

import { AssistantChatTransport } from "@assistant-ui/ai-sdk";
import {
  buildDigichatChatHeaders,
  digichatChatUrl,
  type DigichatCliRequestOptions,
} from "./chat-request.js";

export function createDigichatTransport(opts: DigichatCliRequestOptions) {
  return new AssistantChatTransport({
    api: digichatChatUrl(opts.baseUrl),
    headers: buildDigichatChatHeaders(opts),
  });
}
