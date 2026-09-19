/**
 * Read citation sources from AI SDK UIMessage parts (2.0 wire).
 * Prefer source-* parts; fall back to 1.4 data-digichatActivity hydrate only
 * when no standard sources exist.
 */
import type { UIMessage } from "ai";
import { citationHits } from "@digithings/digichat-ui";
import { messageActivities } from "@/lib/chat-activity";

export type MessageSourceCitation = { title: string; path: string };

function fromStandardParts(message: UIMessage): MessageSourceCitation[] {
  const out: MessageSourceCitation[] = [];
  for (const part of message.parts ?? []) {
    if (!part || typeof part !== "object" || !("type" in part)) continue;
    if (part.type === "source-url") {
      const url = "url" in part && typeof part.url === "string" ? part.url : "";
      const title =
        "title" in part && typeof part.title === "string" && part.title.trim()
          ? part.title
          : url;
      if (url || title) out.push({ title, path: url });
      continue;
    }
    if (part.type === "source-document") {
      const filename =
        "filename" in part && typeof part.filename === "string" ? part.filename : "";
      const title =
        "title" in part && typeof part.title === "string" && part.title.trim()
          ? part.title
          : filename;
      if (filename || title) out.push({ title, path: filename });
    }
  }
  return out;
}

/** Citations for copy/export. Standard parts first; branded hydrate only as fallback. */
export function messageSourceCitations(message: UIMessage): MessageSourceCitation[] {
  const standard = fromStandardParts(message);
  if (standard.length) return standard;
  return citationHits(messageActivities(message)).map((h) => ({
    title: h.title,
    path: h.path,
  }));
}
