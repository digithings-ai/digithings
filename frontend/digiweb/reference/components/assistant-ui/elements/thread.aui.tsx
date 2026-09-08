"use client";

/**
 * Gallery `/chatbot` Thread is the same module the product `digichat` skin
 * mounts. Import the `@digithings/web/chat/thread` subpath — never the
 * `@digithings/web` main barrel (webpack OOM).
 */
export {
  Thread,
  type ComposerLayout,
  type ThreadComponents,
  type ThreadGroupPart,
  type ThreadProps,
} from "@digithings/web/chat/thread";
