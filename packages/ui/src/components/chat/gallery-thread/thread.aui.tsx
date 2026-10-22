"use client";

import {
  ComposerAddAttachment,
  ComposerAttachments,
  HiddenAttachmentNamesProvider,
  UserMessageAttachments,
  useHiddenAttachmentNames,
} from "./attachment.aui";
import { File } from "./file";
import { ThreadFollowupSuggestions } from "./follow-up-suggestions.aui";
import { Image } from "./image";
import { MarkdownText } from "./markdown-text";
import {
  Reasoning,
  ReasoningContent,
  ReasoningRoot,
  ReasoningText,
  ReasoningTrigger,
} from "../stock/reasoning.aui";
import { MessageTiming } from "./message-timing.aui";
import { WorkChain } from "./work-chain";
import { WorkChainSummary } from "./work-chain-summary";
import {
  resolveWorkDisclosure,
  type WorkVisibility,
} from "../stock/skin-types";
import { BackendNotice } from "../stock/chat-notice";
import { ToolFallback } from "../stock/tool-fallback.aui";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "../stock/tool-group.aui";
import {
  CheckActionIcon,
  CopyActionIcon,
} from "./action-icons";
import { TooltipIconButton } from "./tooltip-icon-button";
import { Button } from "../../../ui/button";
import { DotMatrix } from "../DotMatrix";
import { downloadMessageSnapshot, showSnapshotError } from "../../../replay/browser";
import { messageAnchor } from "../../../replay/snapshot";
import { downloadMarkdown } from "../transcript";
import { connectionStatusText } from "../connection-status";
import { WorkStatusLead } from "../work-status-lead";
import { Skeleton } from "../../../ui/skeleton";
import { cn } from "./cn";
import { SkinCredit } from "../stock/skin-credit";
import {
  ActionBarMorePrimitive,
  ActionBarPrimitive,
  AuiIf,
  type AssistantState,
  BranchPickerPrimitive,
  ComposerPrimitive,
  groupPartByType,
  MessagePrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  type FileMessagePartComponent,
  type ImageMessagePartComponent,
  type SourceMessagePartComponent,
  type ToolCallMessagePartComponent,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type ComponentType,
  type FC,
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
  type PropsWithChildren,
  type ReactNode,
} from "react";
import { ComposerTriggerPopover } from "./composer-trigger-popover.aui";
import { MessageError } from "./message-error.aui";
import { ComposerBlockCaret } from "./block-caret";
import { TypedWelcomeCopy } from "./typed-welcome-copy";
import { useDigichatWarmupPhase } from "../use-warmup-phase";
import { OverlayScrollbar } from "../overlay-scrollbar";

export type ThreadGroupPart = MessagePrimitive.GroupedParts.GroupPart;

/**
 * Disclosure behavior for a grouped chain of reasoning / tool-call steps.
 * `off` hides the group entirely, `collapsed` (default) renders a closed
 * dropdown, `balanced` opens while the group is still streaming and
 * auto-collapses when it completes, `expanded` starts open, and
 * `locked_open` pins it open.
 */
export type GroupDisclosureMode =
  | "off"
  | "collapsed"
  | "balanced"
  | "expanded"
  | "locked_open";

/**
 * Optional component overrides for the thread. `AssistantMessage` and
 * `Welcome` replace whole sections; the remaining slots override how the
 * assistant message renders tool calls and part groups. Tool UIs registered
 * by name (toolkit `render`, `useAssistantDataUI`) take precedence over
 * `ToolFallback`.
 */
export type ThreadComponents = {
  AssistantMessage?: ComponentType | undefined;
  Welcome?: ComponentType | undefined;
  ToolFallback?: ToolCallMessagePartComponent | undefined;
  /** Citation row (`source` parts): provider web search, RAG documents (#4552). */
  Source?: SourceMessagePartComponent | undefined;
  /**
   * Optional footer slot below the composer; absent means no footer.
   */
  Footer?: ComponentType | undefined;
  ToolGroup?:
    | ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
    | undefined;
  ReasoningGroup?:
    | ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
    | undefined;
};

/** Expanded: input, then a row of attach + send. Compact: attach | input | send. */
export type ComposerLayout = "expanded" | "compact";

export type ThreadActions = {
  /** Restore previous assistant branch. Default on. */
  undo?: boolean | undefined;
  /** Thumbs up / down. Off when absent. */
  feedback?: boolean | undefined;
};

export type ThreadProps = {
  components?: ThreadComponents | undefined;
  autoFocus?: boolean | undefined;
  /** `chrome.placeholder` in deploy YAML. */
  placeholder?: string | undefined;
  /** `chrome.composerLayout`. Default expanded (toolbar under the input). */
  composerLayout?: ComposerLayout | undefined;
  /** `features.undo` / `features.feedback`. */
  actions?: ThreadActions | undefined;
  /** `chrome.welcome.title`. Used by the default Welcome slot. */
  welcome?: string | undefined;
  /** `chrome.welcome.body`. */
  welcomeBody?: readonly string[] | undefined;
  /**
   * `chrome.suggestions` in deploy YAML. Static prompts for the new-chat
   * welcome state; when non-empty they take precedence over the runtime's own
   * suggestion adapter, which is the fallback.
   */
  suggestions?: readonly string[] | undefined;
  className?: string | undefined;
  /** Embed send-gate / system page-context attach. */
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  /**
   * Native assistant-ui slash adapter (`unstable_useSlashCommandAdapter`).
   * Mounted when the product skin has session prefs (embed, modal, and app).
   */
  slash?: ThreadSlashTrigger | undefined;
  /** Native `@` mention adapter (`unstable_useMentionAdapter`). */
  mention?: ThreadMentionTrigger | undefined;
  /**
   * Attachment names that render no chip in the composer or sent messages.
   * The attachment still lives on the runtime (its file part reaches the
   * model) — only the UI is suppressed. Generic; callers pass system names
   * such as the embed's `page-context.html` in `silent` mode.
   */
  hiddenAttachmentNames?: readonly string[] | undefined;
  /** Disclosure mode for grouped reasoning runs. Default collapsed. */
  reasoningMode?: GroupDisclosureMode | undefined;
  /** Disclosure mode for grouped tool-call runs. Default collapsed. */
  toolCallsMode?: GroupDisclosureMode | undefined;
  /**
   * How much of the agent's work the user sees: `quiet` (the titles only,
   * with the folded header as a live status line), `balanced` (open while it
   * runs, collapsed when it finishes) or `verbose` (stays open). The client's
   * `features.view` picks the default; the user can change it per session.
   */
  workVisibility?: WorkVisibility | undefined;
  /**
   * Rendered as a row inside the composer border, under the input. The
   * digichat skin passes its model / tools / search / view / context chips;
   * other hosts leave it unset.
   */
  composerToolbar?: ReactNode;
  /** `always` reserves a scrollbar gutter; `auto` shows bars only on scroll. */
  scrollbars?: "always" | "auto";
  /** Worked-chain rhythm. `default` is the fixed spacing. */
  density?: "compact" | "default" | "airy";
};

/** `{ adapter, action }` from `unstable_useSlashCommandAdapter`. */
type SlashPopoverProps = ComponentPropsWithoutRef<typeof ComposerTriggerPopover>;
export type ThreadSlashTrigger = {
  adapter: SlashPopoverProps["adapter"];
  action: NonNullable<SlashPopoverProps["action"]>;
  iconMap?: SlashPopoverProps["iconMap"];
  matcher?: SlashPopoverProps["matcher"];
};

export type ThreadMentionTrigger = {
  adapter: SlashPopoverProps["adapter"];
  directive: NonNullable<SlashPopoverProps["directive"]>;
  iconMap?: SlashPopoverProps["iconMap"];
};

/**
 * The chain grouping.
 *
 * A source or a status part between two work runs must not split the chain:
 * only text ends a work run, so two runs with nothing but a source between
 * them are one chain, not two. The library's helper covers the part types it
 * knows; the status parts (`data-*`) are matched here, and the memo
 * fingerprint is kept so the tree is not rebuilt on every render.
 */
const chainGroupBy = (() => {
  const base = groupPartByType({
    reasoning: ["group-chainOfThought", "group-reasoning"],
    "tool-call": ["group-chainOfThought", "group-tool"],
    "standalone-tool-call": [],
    source: ["group-chainOfThought", "group-tool"],
  });
  const fn = (part: { type: string; name?: string }, context?: unknown) => {
    const dataName =
      part.type === "data"
        ? part.name
        : part.type.startsWith("data-")
          ? part.type.slice("data-".length)
          : undefined;
    // A data-notice (tool-call limit, and any other status notice) stays
    // outside the chain. The chain folds once the answer arrives, which would
    // hide the notice inside the collapsed work block.
    if (dataName === "notice") return base(part as never, context as never);
    if (part.type === "data" || part.type.startsWith("data-")) {
      return ["group-chainOfThought", "group-tool"] as const;
    }
    return base(part as never, context as never);
  };
  (fn as unknown as Record<symbol, string>)[
    Symbol.for("@assistant-ui/groupBy.memoKey")
  ] = "digichat:chain-v3";
  return fn;
})();

const DEFAULT_THREAD_ACTIONS: Required<ThreadActions> = {
  undo: true,
  feedback: false,
};

const ThreadActionsContext = createContext<Required<ThreadActions>>(
  DEFAULT_THREAD_ACTIONS,
);

const EMPTY_COMPONENTS: ThreadComponents = {};

const ThreadComponentsContext =
  createContext<ThreadComponents>(EMPTY_COMPONENTS);

type ThreadGroupDisclosure = {
  reasoning: GroupDisclosureMode;
  toolCalls: GroupDisclosureMode;
  visibility: WorkVisibility;
};

const DEFAULT_GROUP_DISCLOSURE: ThreadGroupDisclosure = {
  reasoning: "collapsed",
  toolCalls: "collapsed",
  visibility: "balanced",
};

const ThreadGroupDisclosureContext = createContext<ThreadGroupDisclosure>(
  DEFAULT_GROUP_DISCLOSURE,
);

type ThreadChrome = {
  welcome: string;
  welcomeBody: readonly string[];
  suggestions: readonly string[];
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  className?: string;
  slash?: ThreadSlashTrigger;
  mention?: ThreadMentionTrigger;
};

const EMPTY_SUGGESTIONS: readonly string[] = [];

const DEFAULT_CHROME: ThreadChrome = {
  welcome: "How can I help you today?",
  welcomeBody: [],
  suggestions: EMPTY_SUGGESTIONS,
};

const ThreadChromeContext = createContext<ThreadChrome>(DEFAULT_CHROME);

/** The scroll viewport element, for footer widgets that live outside it. */
const ThreadViewportElContext = createContext<HTMLElement | null>(null);

/**
 * Edit-in-composer: clicking edit on a user message loads its text into the
 * main composer (the only place messages are typed or changed). Resubmitting
 * replaces that message and regenerates from it; unchanged text is a no-op
 * (treated as a misclick), as is an empty or whitespace-only composer.
 * Escape or a click outside the composer cancels and restores whatever draft
 * was there before. The composer itself carries no editing chrome: it looks
 * like a normal text box while a message is being edited.
 */
type ComposerEditState = {
  messageId: string;
  original: string;
  savedDraft: string;
};
type ComposerEditApi = {
  editing: ComposerEditState | null;
  begin: (messageId: string, text: string) => void;
  cancel: () => void;
  commit: (text: string) => void;
};
const ComposerEditContext = createContext<ComposerEditApi>({
  editing: null,
  begin: () => {},
  cancel: () => {},
  commit: () => {},
});

export function isUnchangedEdit(original: string, next: string): boolean {
  return original.trim() === next.trim();
}

/**
 * Should an in-composer edit be sent at all?
 *
 * No when the composer is empty or holds only whitespace (there is nothing to
 * say), and no when the text is the message being edited (an edit that
 * changes nothing is not worth a resend). Both cases end the edit without
 * touching the message.
 */
export function shouldCommitEdit(original: string, next: string): boolean {
  if (!next.trim()) return false;
  return !isUnchangedEdit(original, next);
}

const ComposerEditProvider: FC<PropsWithChildren> = ({ children }) => {
  const aui = useAui();
  const [editing, setEditing] = useState<ComposerEditState | null>(null);
  const editingRef = useRef<ComposerEditState | null>(null);
  editingRef.current = editing;

  const begin = useCallback(
    (messageId: string, text: string) => {
      const prev = editingRef.current;
      const savedDraft = prev ? prev.savedDraft : aui.composer().getState().text;
      aui.composer().setText(text);
      setEditing({ messageId, original: text, savedDraft });
    },
    [aui],
  );
  const cancel = useCallback(() => {
    const cur = editingRef.current;
    if (!cur) return;
    aui.composer().setText(cur.savedDraft);
    setEditing(null);
  }, [aui]);
  const commit = useCallback(
    (text: string) => {
      const cur = editingRef.current;
      if (!cur) return;
      if (!shouldCommitEdit(cur.original, text)) {
        cancel();
        return;
      }
      const mc = aui.thread().message({ id: cur.messageId }).composer();
      mc.beginEdit();
      mc.setText(text);
      mc.send();
      aui.composer().setText(cur.savedDraft);
      setEditing(null);
    },
    [aui, cancel],
  );
  const value = useMemo(
    () => ({ editing, begin, cancel, commit }),
    [editing, begin, cancel, commit],
  );
  return (
    <ComposerEditContext.Provider value={value}>
      {children}
    </ComposerEditContext.Provider>
  );
};
// Startup exposes a loading placeholder thread; treat it as a new chat so
// Welcome docks in the footer above the composer. Loads after startup keep
// the docked layout.
const isNewChatView = (s: AssistantState) =>
  s.thread.messages.length === 0 &&
  (!s.thread.isLoading || s.threads.isLoading);

// A switched thread that is still fetching its history: skeleton, not welcome.
const isHistoryLoadingView = (s: AssistantState) =>
  s.thread.messages.length === 0 &&
  s.thread.isLoading &&
  !s.thread.isDisabled &&
  !s.threads.isLoading;

const ThreadHistorySkeleton: FC = () => (
  <div
    data-slot="aui_thread-history-skeleton"
    role="status"
    className="animate-in fade-in fill-mode-both flex flex-col gap-y-6 [animation-delay:150ms] [animation-duration:200ms]"
  >
    <span className="sr-only">Loading conversation</span>
    <Skeleton variant="block" className="ms-auto h-9 w-2/5 rounded-xl motion-reduce:animate-none" />
    <div className="flex flex-col gap-y-2">
      <Skeleton variant="line" className="h-4 w-11/12 motion-reduce:animate-none" />
      <Skeleton variant="line" className="h-4 w-4/5 motion-reduce:animate-none" />
      <Skeleton variant="line" className="h-4 w-3/5 motion-reduce:animate-none" />
    </div>
    <Skeleton variant="block" className="ms-auto h-9 w-1/3 rounded-xl motion-reduce:animate-none" />
    <div className="flex flex-col gap-y-2">
      <Skeleton variant="line" className="h-4 w-10/12 motion-reduce:animate-none" />
      <Skeleton variant="line" className="h-4 w-2/3 motion-reduce:animate-none" />
    </div>
  </div>
);

const EMPTY_HIDDEN_ATTACHMENTS: readonly string[] = [];

export const Thread: FC<ThreadProps> = ({
  components = EMPTY_COMPONENTS,
  autoFocus = true,
  placeholder,
  composerLayout = "expanded",
  actions,
  welcome,
  welcomeBody,
  suggestions,
  className,
  onComposerSubmit,
  slash,
  mention,
  hiddenAttachmentNames,
  reasoningMode = "collapsed",
  toolCallsMode = "collapsed",
  workVisibility = "balanced",
  composerToolbar,
  scrollbars = "always",
  density = "default",
}) => {
  const resolvedActions: Required<ThreadActions> = {
    undo: actions?.undo !== false,
    feedback: actions?.feedback === true,
  };
  const chrome: ThreadChrome = {
    welcome: welcome ?? DEFAULT_CHROME.welcome,
    welcomeBody: welcomeBody ?? DEFAULT_CHROME.welcomeBody,
    suggestions: suggestions ?? EMPTY_SUGGESTIONS,
    onComposerSubmit,
    className,
    slash,
    mention,
  };
  return (
    <HiddenAttachmentNamesProvider names={hiddenAttachmentNames ?? EMPTY_HIDDEN_ATTACHMENTS}>
      <ThreadChromeContext.Provider value={chrome}>
        <ThreadActionsContext.Provider value={resolvedActions}>
          <ThreadComponentsContext.Provider value={components}>
            <ThreadGroupDisclosureContext.Provider
              value={{
                reasoning: reasoningMode,
                toolCalls: toolCallsMode,
                visibility: workVisibility,
              }}
            >
              <ComposerEditProvider>
                <ThreadRoot
                  autoFocus={autoFocus}
                  placeholder={placeholder}
                  composerLayout={composerLayout}
                  composerToolbar={composerToolbar}
                  scrollbars={scrollbars}
                  density={density}
                />
              </ComposerEditProvider>
            </ThreadGroupDisclosureContext.Provider>
          </ThreadComponentsContext.Provider>
        </ThreadActionsContext.Provider>
      </ThreadChromeContext.Provider>
    </HiddenAttachmentNamesProvider>
  );
};

/**
 * Default branding footer: "powered by digichat" in normal flow below the
 * composer in every state. This footer's `sticky bottom-0 mt-auto` docks it
 * to the page bottom unconditionally, so in-flow is already bottom-pinned —
 * an absolute overlay would paint over the composer (it did; the textbox
 * cut the credit off in app, product, and embed modes). Hosts can still
 * override the whole Footer slot.
 */
const ThreadFooter: FC = () => <SkinCredit />;

const ThreadRoot: FC<{
  autoFocus: boolean;
  placeholder?: string | undefined;
  composerLayout: ComposerLayout;
  composerToolbar?: ReactNode;
  scrollbars: "always" | "auto";
  density: "compact" | "default" | "airy";
}> = ({ autoFocus, placeholder, composerLayout, composerToolbar, scrollbars, density }) => {
  const { Welcome = ThreadWelcome, Footer = ThreadFooter } =
    useContext(ThreadComponentsContext);
  const { className } = useContext(ThreadChromeContext);
  const [viewportEl, setViewportEl] = useState<HTMLElement | null>(null);
  const viewportRef = useRef<HTMLElement | null>(null);
  const attachViewport = useCallback((node: HTMLElement | null) => {
    viewportRef.current = node;
    setViewportEl(node);
  }, []);

  return (
    <ThreadPrimitive.Root
      className={cn(
        "aui-root aui-thread-root digichat-thread bg-background @container flex h-full flex-col",
        className,
      )}
      data-user-align="left"
      // The skin scope marker: `apps/reference/…/chatbot.css` carries the whole
      // first-party theme under `:is(.aui-theme-stage, [data-thread-skin="digichat"])`
      // and the portal mirrors under `html:has([data-thread-skin="digichat"])`.
      // Declaring it here means every mount path gets the same theme — the
      // /baseline catalog, the embed shell, and the production shells — instead
      // of each surface having to remember to wrap the Thread.
      data-thread-skin="digichat"
      data-scrollbars={scrollbars}
      data-density={density}
      style={{
        ["--thread-max-width" as string]: "44rem",
        // `--card` (not `--color-card`) so a scoped palette wins: the
        // Tailwind bridge declares `--color-card` at :root, so its var()
        // resolves there and ignores `.digichat-thread`'s own `--card`.
        ["--composer-bg" as string]: "var(--card)",
        ["--composer-radius" as string]: "0",
        ["--composer-padding" as string]: "8px",
      }}
    >
      {/* The footer (composer + credit) sits outside the scroll viewport so
          messages end above the text box. ViewportProvider keeps the
          scroll-to-bottom control wired to the viewport store. */}
      <ThreadPrimitive.ViewportProvider>
      <ThreadViewportElContext.Provider value={viewportEl}>
      <div className="relative flex min-h-0 flex-1 flex-col">
      <ThreadPrimitive.Viewport
        ref={attachViewport}
        turnAnchor="top"
        // The top-anchored message carries `padding-top: 1.5rem` (chat-aui.css)
        // so it does not sit flush against the viewport top. `tallerThan` scores
        // the anchor's offsetHeight, which includes that padding, so it is
        // raised by the same 1.5rem to keep the set of fully-pinned messages
        // unchanged from before the padding was added.
        topAnchorMessageClamp={{ tallerThan: "11.5em", visibleHeight: "6em" }}
        data-slot="aui_thread-viewport"
        className="relative flex min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-scroll scroll-smooth digichat-thread__viewport"
      >
        <div className="mx-auto flex w-full max-w-(--thread-max-width) flex-1 flex-col px-4 pt-4">
          <AuiIf condition={isHistoryLoadingView}>
            <ThreadHistorySkeleton />
          </AuiIf>

          <div
            data-slot="aui_message-group"
            className="mb-4 flex flex-col gap-y-6 empty:hidden"
          >
            <ThreadPrimitive.Messages>
              {() => <ThreadMessage />}
            </ThreadPrimitive.Messages>
          </div>
        </div>
      </ThreadPrimitive.Viewport>
      <OverlayScrollbar targetRef={viewportRef} width={10} />
      </div>
        <div className="mx-auto flex w-full max-w-(--thread-max-width) shrink-0 flex-col px-4">
          <div className="aui-thread-viewport-footer digichat-thread__footer bg-background relative flex flex-col gap-4 overflow-visible pt-2 pb-2 md:pb-3">
            <ThreadScrollToBottom />
            <ThreadFollowupSuggestions />
            <AuiIf condition={isNewChatView}>
              <div
                data-slot="aui_thread-empty"
                className="aui-thread-empty flex flex-col gap-3"
              >
                <Welcome />
                <ThreadSuggestions />
              </div>
            </AuiIf>
            <Composer
              autoFocus={autoFocus}
              placeholder={placeholder}
              layout={composerLayout}
              toolbar={composerToolbar}
            />
            {Footer ? <Footer /> : null}
          </div>
        </div>
      </ThreadViewportElContext.Provider>
      </ThreadPrimitive.ViewportProvider>
    </ThreadPrimitive.Root>
  );
};

const ThreadMessage: FC = () => {
  const { AssistantMessage: AssistantMessageComponent = AssistantMessage } =
    useContext(ThreadComponentsContext);
  const role = useAuiState((s) => s.message.role);
  // Edits happen in the main composer (ComposerEditProvider); a message's own
  // edit composer is only opened transiently to submit, so never render it.
  if (role === "user") return <UserMessage />;
  return <AssistantMessageComponent />;
};

const ThreadScrollToBottom: FC = () => {
  const viewportEl = useContext(ThreadViewportElContext);
  const [revealSettled, setRevealSettled] = useState(false);
  const [scrolledAway, setScrolledAway] = useState(false);

  // Arm only after the bottom-up entrance has finished - the button used to
  // pop in mid-animation.
  useEffect(() => {
    const owner = viewportEl?.closest("[data-stock-product]");
    if (!owner) {
      setRevealSettled(true);
      return;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      if (owner.getAttribute("data-boot-reveal") !== "true") return;
      observer.disconnect();
      timer = setTimeout(() => setRevealSettled(true), 950);
    };
    const observer = new MutationObserver(arm);
    observer.observe(owner, {
      attributes: true,
      attributeFilter: ["data-boot-reveal"],
    });
    arm();
    return () => {
      observer.disconnect();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [viewportEl]);

  // Show only when content is actually hidden under the composer: the message
  // list's bottom must sit below the top edge of the composer shell. A scroll
  // of a few pixels with everything still visible (e.g. after the entrance
  // settle) must not surface it.
  useEffect(() => {
    if (!viewportEl) return;
    let observedGroup: HTMLElement | null = null;
    let observedComposer: HTMLElement | null = null;
    const measure = () => {
      // Re-query each run: neither node is guaranteed to be mounted yet (and
      // either may remount), so a captured reference could go stale.
      const group = viewportEl.querySelector<HTMLElement>(
        '[data-slot="aui_message-group"]',
      );
      // The composer sits below the scroll viewport, on the thread root.
      const composer = (
        viewportEl.closest(".aui-thread-root") ?? viewportEl
      ).querySelector<HTMLElement>('[data-slot="aui_composer-shell"]');
      if (!group || !composer) {
        setScrolledAway(false);
        return;
      }
      if (group !== observedGroup) {
        if (observedGroup) ro.unobserve(observedGroup);
        ro.observe(group);
        observedGroup = group;
      }
      if (composer !== observedComposer) {
        if (observedComposer) ro.unobserve(observedComposer);
        ro.observe(composer);
        observedComposer = composer;
      }
      setScrolledAway(
        group.getBoundingClientRect().bottom >
          composer.getBoundingClientRect().top + 1,
      );
    };
    const ro = new ResizeObserver(measure);
    measure();
    viewportEl.addEventListener("scroll", measure, { passive: true });
    ro.observe(viewportEl);
    return () => {
      viewportEl.removeEventListener("scroll", measure);
      ro.disconnect();
    };
  }, [viewportEl]);

  if (!revealSettled || !scrolledAway) return null;

  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <TooltipIconButton
        tooltip="Scroll to bottom"
        variant="outline"
        className="aui-thread-scroll-to-bottom dark:border-border dark:bg-background dark:hover:bg-accent absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible"
      >
        <DotMatrix state="scroll" decorative className="size-3.5" />
      </TooltipIconButton>
    </ThreadPrimitive.ScrollToBottom>
  );
};

const ThreadWelcome: FC = () => {
  const { welcome, welcomeBody } = useContext(ThreadChromeContext);
  return (
    <div
      data-slot="aui_thread-welcome"
      className="aui-thread-welcome-root flex flex-col items-start text-start"
    >
      <h1 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in fill-mode-both text-2xl font-medium tracking-tight duration-200">
        {welcome}
      </h1>
      <TypedWelcomeCopy lines={welcomeBody} />
    </div>
  );
};

/**
 * Shared look for a welcome prompt row. The runtime-backed item and the static
 * fallback render the same markup so a skin's examples look identical whether
 * they came from the runtime or from `chrome.suggestions`.
 */
const SUGGESTION_BUTTON_CLASS =
  "aui-thread-welcome-suggestion fade-in slide-in-from-bottom-1 animate-in fill-mode-both grid w-full cursor-pointer grid-cols-[1.25rem_minmax(0,1fr)] items-start gap-x-[0.55rem] rounded-none border-0 bg-transparent px-0 py-0.5 text-start text-sm font-normal duration-200";

const ThreadSuggestions: FC = () => {
  const { suggestions } = useContext(ThreadChromeContext);
  return (
    <div className="aui-thread-welcome-suggestions flex w-full flex-col items-stretch gap-0.5">
      {suggestions.length > 0 ? (
        suggestions.map((prompt, index) => (
          <StaticSuggestionItem key={`${index}:${prompt}`} prompt={prompt} />
        ))
      ) : (
        <ThreadPrimitive.Suggestions>
          {() => <ThreadSuggestionItem />}
        </ThreadPrimitive.Suggestions>
      )}
    </div>
  );
};

/** Static `chrome.suggestions` prompt. Appends the text like a typed message. */
const StaticSuggestionItem: FC<{ prompt: string }> = ({ prompt }) => {
  const aui = useAui();
  return (
    <button
      type="button"
      onClick={() => {
        if (aui.thread.getState().isRunning) return;
        aui.thread.append({
          content: [{ type: "text", text: prompt }],
          runConfig: aui.composer.getState().runConfig,
        });
      }}
      className={SUGGESTION_BUTTON_CLASS}
    >
      <span className="aui-msg-marker" aria-hidden="true">
        <DotMatrix
          state="example"
          decorative
          className="aui-thread-welcome-suggestion-mark size-3.5"
        />
      </span>
      <span className="aui-thread-welcome-suggestion-text min-w-0">
        <span className="aui-thread-welcome-suggestion-text-1">{prompt}</span>
      </span>
    </button>
  );
};

const ThreadSuggestionItem: FC = () => {
  return (
    <SuggestionPrimitive.Trigger send asChild>
      <button type="button" className={SUGGESTION_BUTTON_CLASS}>
        <span className="aui-msg-marker" aria-hidden="true">
          <DotMatrix
            state="example"
            decorative
            className="aui-thread-welcome-suggestion-mark size-3.5"
          />
        </span>
        <span className="aui-thread-welcome-suggestion-text min-w-0">
          <SuggestionPrimitive.Title className="aui-thread-welcome-suggestion-text-1" />
          <SuggestionPrimitive.Description className="aui-thread-welcome-suggestion-text-2 empty:hidden" />
        </span>
      </button>
    </SuggestionPrimitive.Trigger>
  );
};

const Composer: FC<{
  autoFocus: boolean;
  placeholder?: string | undefined;
  layout: ComposerLayout;
  toolbar?: ReactNode;
}> = ({ autoFocus, placeholder = "Send a message...", layout, toolbar }) => {
  const compact = layout === "compact";
  const { onComposerSubmit, slash, mention } = useContext(ThreadChromeContext);
  const edit = useContext(ComposerEditContext);
  const aui = useAui();
  const inputWrapRef = useRef<HTMLDivElement | null>(null);
  const composerRootRef = useRef<HTMLFormElement | null>(null);
  const isEditingMessage = edit.editing !== null;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    if (edit.editing) {
      event.preventDefault();
      edit.commit(aui.composer().getState().text);
      return;
    }
    onComposerSubmit?.(event);
  };

  // Click outside the composer cancels an in-progress edit. The edit button
  // itself is excluded so re-clicking edit on another message switches target.
  useEffect(() => {
    if (!isEditingMessage) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target) return;
      if (composerRootRef.current?.contains(target)) return;
      if (target.closest(".aui-user-action-edit, [data-radix-popper-content-wrapper]")) return;
      edit.cancel();
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [isEditingMessage, edit]);

  // Focus the composer when an edit starts.
  useEffect(() => {
    if (!isEditingMessage) return;
    const area = inputWrapRef.current?.querySelector<HTMLTextAreaElement>("textarea");
    if (!area) return;
    area.focus({ preventScroll: true });
    const end = area.value.length;
    area.setSelectionRange(end, end);
  }, [isEditingMessage, edit.editing?.messageId]);
  const focusComposerInput = () => {
    inputWrapRef.current
      ?.querySelector<HTMLTextAreaElement>("textarea")
      ?.focus({ preventScroll: true });
  };

  // Focus the composer on mount. The runtime's own autoFocus effect can miss
  // when the embed hydrates inside an iframe, and a retry covers engines that
  // ignore focus() until the first paint.
  useEffect(() => {
    if (!autoFocus) return;
    let cancelled = false;
    let attempts = 0;
    const focus = () => {
      if (cancelled) return;
      const area =
        inputWrapRef.current?.querySelector<HTMLTextAreaElement>("textarea");
      if (!area || document.activeElement === area) return;
      const active = document.activeElement;
      if (active instanceof HTMLElement && active !== document.body) return;
      area.focus({ preventScroll: true });
      if (document.activeElement !== area && attempts < 6) {
        attempts += 1;
        window.requestAnimationFrame(focus);
      }
    };
    const frame = window.requestAnimationFrame(focus);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
    };
  }, [autoFocus]);

  const handleShellMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement | null;
    if (
      target?.closest(
        "button, a, input, textarea, select, [contenteditable='true']",
      )
    ) {
      return;
    }
    event.preventDefault();
    focusComposerInput();
  };
  const bar = (
    <ComposerPrimitive.Root
      ref={composerRootRef}
      className="aui-composer-root relative flex w-full flex-col"
      onSubmit={handleSubmit}
      onKeyDownCapture={(event) => {
        if (isEditingMessage && event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          edit.cancel();
        }
      }}
    >
      <ComposerPrimitive.AttachmentDropzone asChild>
        <div
          data-slot="aui_composer-shell"
          data-layout={layout}
          onMouseDown={handleShellMouseDown}
          className="border-border/60 data-[dragging=true]:border-ring dark:border-muted-foreground/15 flex w-full cursor-text flex-col gap-2 rounded-(--composer-radius) border bg-(--composer-bg) p-(--composer-padding) data-[dragging=true]:border-dashed data-[dragging=true]:bg-[color-mix(in_oklab,var(--color-accent)_50%,var(--color-background))]"
        >
          <ComposerAttachments />
          {/* One row: attach, input, send. The toolbar used to sit on a second
              row inside the same border, which read as a two-line text box. */}
          <div className="aui-composer-main flex min-w-0 items-end gap-1">
            <ComposerAddAttachment />
            <div
              ref={inputWrapRef}
              className="aui-composer-input-wrap relative min-w-0 flex-1"
            >
              <ComposerPrimitive.Input
                placeholder={placeholder}
                className={cn(
                  "aui-composer-input placeholder:text-muted-foreground/60 w-full resize-none overflow-x-hidden overflow-y-auto break-words whitespace-pre-wrap bg-transparent outline-none",
                  compact
                    ? "min-h-7 max-h-[8.75rem] px-1.5 py-0 text-sm leading-7"
                    : "min-h-[1.375rem] max-h-[7.75rem] px-2.5 py-0.5 text-base leading-6",
                )}
                rows={1}
                maxRows={5}
                autoFocus={autoFocus}
                submitMode="enter"
                enterKeyHint="send"
                aria-label="Message"
              />
              <ComposerBlockCaret containerRef={inputWrapRef} />
            </div>
            <ComposerSendControls />
          </div>
        </div>
      </ComposerPrimitive.AttachmentDropzone>
      {toolbar ? (
        <div data-slot="aui_composer-toolbar" className="aui-composer-toolbar">
          {toolbar}
        </div>
      ) : null}
      {slash ? (
        <ComposerTriggerPopover
          char="/"
          adapter={slash.adapter}
          action={slash.action}
          iconMap={slash.iconMap}
          matcher={slash.matcher}
          emptyItemsLabel="No matching commands"
        />
      ) : null}
      {mention ? (
        <ComposerTriggerPopover
          char="@"
          adapter={mention.adapter}
          directive={mention.directive}
          iconMap={mention.iconMap}
          emptyItemsLabel="No matching tools"
        />
      ) : null}
    </ComposerPrimitive.Root>
  );
  if (!slash && !mention) return bar;
  return (
    <ComposerPrimitive.Unstable_TriggerPopoverRoot>
      {bar}
    </ComposerPrimitive.Unstable_TriggerPopoverRoot>
  );
};

const ComposerSendControls: FC = () => {
  const aui = useAui();
  // Mirrors `composerSendDisabled` from `@assistant-ui/core`'s primitive
  // predicates. Inlined rather than imported: the predicate is not re-exported
  // from `@assistant-ui/react` (the only assistant-ui package this one depends
  // on), so a deep import would resolve only thanks to npm hoisting.
  const sendDisabled = useAuiState(
    (s) => !s.composer.canSend || (s.thread.isRunning && !s.thread.capabilities.queue),
  );
  // A `type="submit"` button already submits its form on activation, so the
  // click must not also do it: `preventDefault()` suppresses that implicit
  // submission, and the explicit `requestSubmit()` below replaces it with one
  // we control. Without this the form's `submit` fires twice per click, and the
  // free-turn gate mounted on `onSubmit` runs twice — holding or charging the
  // turn more than once.
  const submitComposer = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const form = event.currentTarget.closest("form");
    if (form) {
      form.requestSubmit();
      return;
    }
    aui.composer.send();
  };

  return (
      <div className="aui-composer-send-controls ml-auto flex shrink-0 items-center gap-1.5">
      <AuiIf condition={(s) => s.thread.capabilities.dictation}>
        <AuiIf condition={(s) => s.composer.dictation == null}>
          <ComposerPrimitive.Dictate asChild>
            <TooltipIconButton
              tooltip="Voice input"
              side="bottom"
              type="button"
              variant="ghost"
              size="icon"
              className="aui-composer-dictate text-muted-foreground hover:text-foreground size-7 rounded-full"
              aria-label="Start voice input"
            >
              <DotMatrix
                state="dictate"
                decorative
                className="aui-composer-dictate-icon size-3.5"
              />
            </TooltipIconButton>
          </ComposerPrimitive.Dictate>
        </AuiIf>
        <AuiIf condition={(s) => s.composer.dictation != null}>
          <ComposerPrimitive.StopDictation asChild>
            <TooltipIconButton
              tooltip="Stop dictation"
              side="bottom"
              type="button"
              variant="ghost"
              size="icon"
              className="aui-composer-stop-dictation text-destructive size-7 rounded-full"
              aria-label="Stop voice input"
            >
              <DotMatrix
                state="stop"
                decorative
                className="aui-composer-stop-dictation-icon size-3.5"
              />
            </TooltipIconButton>
          </ComposerPrimitive.StopDictation>
        </AuiIf>
      </AuiIf>
      <AuiIf condition={(s) => !s.thread.isRunning}>
        {/* No tooltip/dropdown on send: the button submits on click and on
            Enter, so the "Send (Enter)" popover was noise. */}
        <Button
          dress="chat"
          type="submit"
          variant="ghost"
          size="icon"
          className="aui-composer-send size-7 rounded-full"
          aria-label="Send message"
          disabled={sendDisabled}
          onClick={submitComposer}
        >
          <DotMatrix
            state="send"
            decorative
            className="aui-composer-send-icon size-3.5"
          />
        </Button>
      </AuiIf>
      <AuiIf condition={(s) => s.thread.isRunning}>
        <ComposerPrimitive.Cancel asChild>
          <Button dress="chat"
            type="button"
            variant="default"
            size="icon"
            className="aui-composer-cancel size-7 rounded-full"
            aria-label="Stop generating"
          >
            <DotMatrix
              state="stop"
              decorative
              className="aui-composer-cancel-icon size-3.5"
            />
          </Button>
        </ComposerPrimitive.Cancel>
      </AuiIf>
    </div>
  );
};

/** Thread-level cubes only when no tool is already animating its own matrix. */
const AssistantWorkingIndicator: FC = () => {
  const toolRunning = useAuiState((s) =>
    s.message.parts.some(
      (part) => part.type === "tool-call" && part.status.type === "running",
    ),
  );
  // Text only when the server sent a status message (DIG-4459): a bare
  // `connecting` is the plain wait for a response, so the row is the
  // animation alone. No client-side default copy.
  const statusText = useAuiState((s) => connectionStatusText(s.message.parts));
  const wakePhase = useDigichatWarmupPhase();
  if (toolRunning) return null;
  const statusLabel = wakePhase === "waking" ? "Waking up services…" : statusText;
  return (
    <span
      data-slot="aui_assistant-message-indicator"
      className="aui-work-status"
    >
      <WorkStatusLead
        marker="loading"
        markerLabel="Assistant is working"
        label={statusLabel}
      />
    </span>
  );
};

const AssistantMessage: FC = () => {
  const {
    ToolFallback: ToolFallbackComponent = ToolFallback,
    ToolGroup,
    ReasoningGroup,
  } = useContext(ThreadComponentsContext);
  const {
    reasoning: reasoningMode,
    toolCalls: toolCallsMode,
    visibility,
  } = useContext(ThreadGroupDisclosureContext);
  const disclosure = resolveWorkDisclosure(visibility);
  // The whole turn, not just the group: the tools answer faster than the
  // chain can fold, and a group that closes between two of them flickers.
  const turnRunning = useAuiState((s) => s.thread.isRunning);
  // The message parts, to tell a chain that holds real work from one that
  // only holds a source or a status part.
  const messageParts = useAuiState((s) => s.message.parts);
  // Only text ends a work run: a chain with a text part after it has
  // answered, so its work is over. A chain without one is still the agent's
  // current work, even if the model streams another run of tool calls.
  const hasWork = messageParts.some(
    (part) => part.type === "reasoning" || part.type === "tool-call",
  );
  // Anything real that arrived from the agent — reasoning, a tool call, the
  // answer itself. A status part (the connection state) is not content: it is
  // the pre-response phase, which is exactly when the loading row belongs.
  const hasContent = messageParts.some((part) => part.type !== "data");
  const followedByText = (indices: readonly number[]) => {
    const last = indices.length > 0 ? indices[indices.length - 1] : -1;
    return messageParts.some((part, index) => {
      if (index <= last) return false;
      if (part.type !== "text") return false;
      const text = (part as { text?: unknown }).text;
      return typeof text === "string" && text.trim() !== "";
    });
  };

  const ACTION_BAR_PT = "pt-1.5";
  // Keep the action bar inside the contained root's paint box, then cancel its reserved space in flow.
  const ACTION_BAR_HEIGHT = `min-h-7.5 ${ACTION_BAR_PT}`;

  return (
    <MessagePrimitive.Root
      data-slot="aui_assistant-message-root"
      data-role="assistant"
      className="aui-msg fade-in slide-in-from-bottom-1 animate-in relative grid grid-cols-[minmax(0,1fr)] items-start -mb-7.5 pb-7.5 duration-150"
    >
      <div
        data-slot="aui_assistant-message-content"
        className="aui-assistant-message-content text-foreground min-w-0 leading-relaxed wrap-break-word"
      >
        <MessagePrimitive.GroupedParts
          groupBy={chainGroupBy}
        >
          {({ part, children }) => {
            switch (part.type) {
              case "group-chainOfThought": {
                // A status part is not work. The grouping puts the
                // connection state into the chain, so without this guard the
                // chain header appears before the model has said anything —
                // right next to the loading row, which is the double
                // animation we do not want. No reasoning and no tool call in
                // the group means no work block: the loading row covers that
                // phase on its own.
                const holdsWork = part.indices.some((index) => {
                  const kind = messageParts[index]?.type;
                  return kind === "reasoning" || kind === "tool-call";
                });
                // The parts still render bare: a backend notice (DIG-4459)
                // rides a data part and must not vanish with the header.
                if (!holdsWork) return <>{children}</>;
                // The chain is the one disclosure boundary: every work part
                // nests under it (see `chainGroupBy`), so the level's fold
                // rule here reaches a reasoning-only, a tool-only and a
                // combined turn alike. The rows inside take their own rule
                // from the same disclosure. See the decision note in
                // packages/ui/ARCHITECTURE.md.
                //
                // The `hidden` level this branch served is retired: the
                // `summaryOnly` field is always false now, and a quiet
                // client gets the folded chain below instead of a summary
                // line. The branch stays until the field goes.
                if (disclosure.summaryOnly) {
                  return (
                    <div data-slot="aui_chain-of-thought">
                      <WorkChainSummary indices={part.indices} />
                    </div>
                  );
                }
                // One header for the whole chain: the reasoning and the tool
                // calls collapse together.
                return (
                  <div data-slot="aui_chain-of-thought">
                    <WorkChain
                      indices={part.indices}
                      openAtRest={disclosure.openAtRest}
                      foldOnAnswer={disclosure.foldOnAnswer}
                      running={part.status.type === "running"}
                      followedByText={followedByText(part.indices)}
                    >
                      {children}
                    </WorkChain>
                  </div>
                );
              }
              case "group-tool": {
                if (toolCallsMode === "off") return null;
                if (ToolGroup) {
                  return <ToolGroup group={part}>{children}</ToolGroup>;
                }
                const locked = toolCallsMode === "locked_open";
                const running = part.status.type === "running";
                // The group can hold the source and status parts that sit
                // between two tool runs; the count is the tool calls only.
                const toolCount = part.indices.filter(
                  (index) => messageParts[index]?.type === "tool-call",
                ).length;
                if (toolCount === 0) {
                  return <div data-slot="aui_chain-of-thought">{children}</div>;
                }
                return (
                  <ToolGroupRoot
                    variant="ghost"
                    defaultOpen={
                      disclosure.openAtRest || toolCallsMode === "expanded" || locked
                    }
                    streamingOpen={
                      (disclosure.openWhileRunning || toolCallsMode === "balanced") &&
                      (running || turnRunning)
                    }
                    {...(locked ? { open: true, onOpenChange: () => {} } : {})}
                  >
                    <ToolGroupTrigger
                      count={toolCount}
                      active={part.status.type === "running"}
                      disabled={locked}
                    />
                    <ToolGroupContent>{children}</ToolGroupContent>
                  </ToolGroupRoot>
                );
              }
              case "group-reasoning": {
                if (reasoningMode === "off") return null;
                if (ReasoningGroup) {
                  return (
                    <ReasoningGroup group={part}>{children}</ReasoningGroup>
                  );
                }
                const running = part.status.type === "running";
                const locked = reasoningMode === "locked_open";
                return (
                  <ReasoningRoot
                    variant="ghost"
                    streaming={
                      (running || turnRunning) &&
                      (disclosure.openWhileRunning || reasoningMode === "balanced")
                    }
                    defaultOpen={
                      disclosure.openAtRest || reasoningMode === "expanded" || locked
                    }
                    {...(locked ? { open: true, onOpenChange: () => {} } : {})}
                  >
                    {/* Upstream's structure: the reasoning is a sub-step with
                        its own disclosure inside the chain. */}
                    <ReasoningTrigger active={running} disabled={locked} />
                    <ReasoningContent aria-busy={running}>
                      <ReasoningText>{children}</ReasoningText>
                    </ReasoningContent>
                  </ReasoningRoot>
                );
              }
              case "text":
                return <MarkdownText />;
              case "reasoning": {
                if (reasoningMode === "off") return null;
                return <Reasoning {...part} />;
              }
              case "tool-call":
                if (toolCallsMode === "off") return null;
                return part.toolUI ?? <ToolFallbackComponent {...part} />;
              case "data":
                // DIG-4459: a backend notice (data-notice, or a data-status
                // with a message) shows as a boxed status/error line.
                return part.dataRendererUI ?? <BackendNotice part={part} />;
              case "file":
                return (
                  <div data-slot="aui_assistant-message-file" className="py-1">
                    <File {...part} />
                  </div>
                );
              case "image":
                return (
                  <div data-slot="aui_assistant-message-image" className="py-1">
                    <Image {...part} />
                  </div>
                );
              case "indicator":
                // One loading affordance per turn. Before the agent answers,
                // the row stands alone (with the phase text when we know it:
                // waking, connecting, warming up). The moment anything real
                // arrives — reasoning, a tool call, the answer — the work
                // block takes over and this row is gone, so the two never
                // stack.
                return hasContent ? null : <AssistantWorkingIndicator />;
              case "source":
                // Citations are inline markdown links in the answer (DIG-1210);
                // rendering source parts here stacked duplicate rows between
                // tool groups on every retrieve span.
                return null;
              default:
                return null;
            }
          }}
        </MessagePrimitive.GroupedParts>
        <MessageError />
      </div>

      <div
        data-slot="aui_assistant-message-footer"
        className={cn("col-start-1 flex items-center", ACTION_BAR_HEIGHT)}
      >
        <AuiIf
          condition={(s) =>
            !(
              s.message.status?.type === "incomplete" &&
              s.message.status.reason === "error"
            )
          }
        >
          <BranchPicker />
          <AssistantActionBar />
        </AuiIf>
      </div>
    </MessagePrimitive.Root>
  );
};

const AssistantActionBar: FC = () => {
  const { undo, feedback } = useContext(ThreadActionsContext);
  const messageId = useAuiState((s) => s.message.id);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const exportMessage = useRef<HTMLElement | null>(null);
  const exportHtmlAfterClose = useRef(false);
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-assistant-action-bar-root text-muted-foreground animate-in fade-in col-start-3 row-start-2 -ms-1 flex gap-1 duration-200"
    >
      <ActionBarPrimitive.Copy asChild>
        <TooltipIconButton tooltip="Copy">
          <AuiIf condition={(s) => s.message.isCopied}>
            <CheckActionIcon className="size-3.5" />
          </AuiIf>
          <AuiIf condition={(s) => !s.message.isCopied}>
            <CopyActionIcon className="size-3.5" />
          </AuiIf>
        </TooltipIconButton>
      </ActionBarPrimitive.Copy>
      {undo ? (
        <AuiIf
          condition={(s) =>
            (s.message.branchCount ?? 1) > 1 && (s.message.branchNumber ?? 1) > 1
          }
        >
          <BranchPickerPrimitive.Previous asChild>
            <TooltipIconButton tooltip="Undo">
              <DotMatrix state="prev" decorative className="size-3.5" />
            </TooltipIconButton>
          </BranchPickerPrimitive.Previous>
        </AuiIf>
      ) : null}
      <ActionBarPrimitive.Reload asChild>
        <TooltipIconButton tooltip="Redo">
          <DotMatrix state="refresh" decorative className="size-3.5" />
        </TooltipIconButton>
      </ActionBarPrimitive.Reload>
      {feedback ? (
        <>
          <ActionBarPrimitive.FeedbackPositive asChild>
            <TooltipIconButton tooltip="Good response">
              <DotMatrix state="thumbsUp" decorative className="size-3.5" />
            </TooltipIconButton>
          </ActionBarPrimitive.FeedbackPositive>
          <ActionBarPrimitive.FeedbackNegative asChild>
            <TooltipIconButton tooltip="Bad response">
              <DotMatrix state="thumbsDown" decorative className="size-3.5" />
            </TooltipIconButton>
          </ActionBarPrimitive.FeedbackNegative>
        </>
      ) : null}
      <ActionBarMorePrimitive.Root
        onOpenChange={(open) => {
          if (open || !exportHtmlAfterClose.current) return;
          exportHtmlAfterClose.current = false;
          const doc = document;
          const message = exportMessage.current;
          exportMessage.current = null;
          const id = messageId;
          requestAnimationFrame(() => {
            void downloadMessageSnapshot(doc, new Date().toISOString(), id, message).catch(
              (error: unknown) => {
                const message = error instanceof Error ? error.message : "HTML export failed.";
                showSnapshotError(doc, message);
              },
            );
          });
        }}
      >
        <ActionBarMorePrimitive.Trigger asChild ref={triggerRef}>
          <TooltipIconButton tooltip="More">
            <DotMatrix state="more" decorative className="size-3.5" />
          </TooltipIconButton>
        </ActionBarMorePrimitive.Trigger>
        <ActionBarMorePrimitive.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="aui-action-bar-more-content z-[110] min-w-[8rem] overflow-hidden border p-1"
        >
          <ActionBarPrimitive.ExportMarkdown
            asChild
            onExport={(content) => {
              downloadMarkdown("digichat.md", content);
            }}
          >
            <ActionBarMorePrimitive.Item className="aui-action-bar-more-item flex cursor-pointer items-center gap-2 bg-transparent px-2 py-1.5 outline-none select-none hover:bg-transparent focus:bg-transparent data-highlighted:bg-transparent data-highlighted:text-ink">
              <DotMatrix state="export" decorative className="size-3.5" />
              Export as Markdown
            </ActionBarMorePrimitive.Item>
          </ActionBarPrimitive.ExportMarkdown>
          <ActionBarMorePrimitive.Item
            className="aui-action-bar-more-item flex cursor-pointer items-center gap-2 bg-transparent px-2 py-1.5 outline-none select-none hover:bg-transparent focus:bg-transparent data-highlighted:bg-transparent data-highlighted:text-ink"
            onClick={() => {
              exportMessage.current = messageAnchor(triggerRef.current, messageId);
              exportHtmlAfterClose.current = true;
            }}
          >
            <DotMatrix state="export" decorative className="size-3.5" />
            Export as HTML
          </ActionBarMorePrimitive.Item>
        </ActionBarMorePrimitive.Content>
      </ActionBarMorePrimitive.Root>
      <MessageTiming />
    </ActionBarPrimitive.Root>
  );
};

const UserFilePart: FileMessagePartComponent = (part) => {
  const hiddenNames = useHiddenAttachmentNames();
  if (part.filename && hiddenNames.includes(part.filename)) return null;
  return (
    <div data-slot="aui_user-message-file" className="py-1">
      <File {...part} />
    </div>
  );
};

const UserImagePart: ImageMessagePartComponent = (part) => (
  <div data-slot="aui_user-message-image" className="py-1">
    <Image {...part} />
  </div>
);

const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_user-message-root"
      className="aui-msg fade-in slide-in-from-bottom-1 animate-in grid grid-cols-[1.25rem_minmax(0,1fr)_1.75rem] items-start gap-x-[0.55rem] gap-y-2 duration-150"
      data-role="user"
    >
      <span className="aui-msg-marker" aria-hidden="true">
        <DotMatrix state="user" label="User" className="size-3.5" />
      </span>
      <div className="aui-user-message-content-wrapper relative min-w-0">
        <UserMessageAttachments />
        <div className="aui-user-message-content text-foreground wrap-break-word empty:hidden">
          <MessagePrimitive.Parts
            components={{ File: UserFilePart, Image: UserImagePart }}
          />
        </div>
      </div>
      <div className="aui-user-action-bar-slot col-start-3 row-start-1 self-start justify-self-end">
        <UserActionBar />
      </div>

      <BranchPicker
        data-slot="aui_user-branch-picker"
        className="col-start-2 -me-1 justify-start"
      />
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => {
  const aui = useAui();
  const edit = useContext(ComposerEditContext);
  const onEdit = () => {
    const msg = aui.message().getState();
    const text = msg.parts
      .map((p) => (p.type === "text" ? p.text : ""))
      .join("");
    edit.begin(msg.id, text);
  };
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-user-action-bar-root flex flex-row items-center"
    >
      <TooltipIconButton
        tooltip="Edit"
        className="aui-user-action-edit"
        onClick={onEdit}
      >
        <DotMatrix state="edit" decorative className="size-3.5" />
      </TooltipIconButton>
    </ActionBarPrimitive.Root>
  );
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
  className,
  ...rest
}) => {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn(
        "aui-branch-picker-root text-muted-foreground -ms-2 me-2 inline-flex items-center text-xs",
        className,
      )}
      {...rest}
    >
      <BranchPickerPrimitive.Previous asChild>
        <TooltipIconButton tooltip="Previous">
          <DotMatrix state="prev" decorative className="size-3.5" />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Next">
          <DotMatrix state="next" decorative className="size-3.5" />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};
