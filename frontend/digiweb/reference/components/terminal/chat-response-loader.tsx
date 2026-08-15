/**
 * Chat response loader — the wait between sending a message and the first token
 * of the answer, occupying the assistant turn it is about to become.
 *
 * PROMOTED to `@digithings/web`; consume it from there. The implementation and
 * the full docblock live in `web/src/components/terminal/ChatResponseLoader.tsx`.
 * A surface that already owns its assistant row renders <TerminalStepCaret>
 * directly instead — see `CHAT_RESPONSE_HOLD_MS`. This file stays as the
 * re-export so the specimen keeps a stable import path.
 */
export {
  ChatResponseLoader,
  CHAT_RESPONSE_STEPS,
  CHAT_RESPONSE_HOLD_MS,
  type ChatResponseLoaderProps,
} from "@digithings/web";
