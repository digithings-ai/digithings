/**
 * Host-provided wiring for the first-party digichat skin (WS4).
 *
 * The skin lives in `@digithings/ui` and cannot import product modules, so
 * the app builds its option object once at module scope (every entry is a
 * static constant or a module function) and passes it as `ThreadSkinView`'s
 * `digichat` prop. Values mirror what `skins/digichat.tsx` consumed directly
 * before WS4: baseline copy fallbacks, the page-context protocol name, and
 * the product slash-command + pending-header functions.
 */
import type { DigichatSkinOptions } from "@digithings/ui/chat/skins";
import {
  BASELINE_EMBED_PLACEHOLDER,
  BASELINE_EMBED_SUGGESTIONS,
  BASELINE_EMBED_WELCOME,
} from "@/lib/baseline-embed";
import { PAGE_CONTEXT_ATTACHMENT_NAME } from "@/lib/embed-page-context-messages";
import {
  armForceToolThenHold,
  setPendingForceTool,
  setPendingWebSearchForce,
} from "@/lib/pending-chat-headers";
import {
  buildProductSlashCommands,
  executeSlashDef,
  executeSlashFromComposer,
  extraSlashDefs,
  prefixSlashAdapter,
  shouldInsertToolDraft,
  slashSubmitAction,
} from "@/lib/product-slash-commands";

export const DIGICHAT_SKIN_OPTIONS: DigichatSkinOptions = {
  copy: {
    welcome: BASELINE_EMBED_WELCOME,
    placeholder: BASELINE_EMBED_PLACEHOLDER,
    suggestions: BASELINE_EMBED_SUGGESTIONS,
  },
  hiddenAttachmentName: PAGE_CONTEXT_ATTACHMENT_NAME,
  slash: {
    buildCommands: buildProductSlashCommands,
    extraDefs: extraSlashDefs,
    prefixAdapter: prefixSlashAdapter,
    shouldDraft: shouldInsertToolDraft,
    submitAction: slashSubmitAction,
    executeDef: executeSlashDef,
    executeFromComposer: executeSlashFromComposer,
    armForceTool: armForceToolThenHold,
    setForceTool: setPendingForceTool,
    setWebSearchForce: setPendingWebSearchForce,
  },
};
