"use client";

import { useEffect } from "react";
import { unstable_useTriggerPopoverScopeContextOptional } from "@assistant-ui/react";
import { committedChatPrefs, slashRowPreview, useEmbedChatPrefsOptional } from "./embed-chat-prefs";

/**
 * Inside the `/` popover: while the highlighted row flips a purely visual
 * setting in place (`/scrollbar`), the page shows the flipped look. Nothing
 * is stored; moving off the row or closing the popover drops the preview,
 * and choosing the row commits it as before.
 */
export function PaletteRowPreview(): null {
  const scope = unstable_useTriggerPopoverScopeContextOptional();
  const api = useEmbedChatPrefsOptional();
  const preview = api?.previewPrefs;
  const id = scope?.open ? scope.items[scope.highlightedIndex]?.id : undefined;
  const patch = id && api ? slashRowPreview(id, committedChatPrefs(api)) : null;
  const key = patch ? JSON.stringify(patch) : "";
  useEffect(() => {
    if (!preview || !key) return;
    preview(JSON.parse(key));
    return () => preview(null);
  }, [preview, key]);
  return null;
}
