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
} from "./reasoning.aui";
import { MessageTiming } from "./message-timing.aui";
import { ToolFallback } from "./tool-fallback.aui";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "./tool-group.aui";
import {
  CheckActionIcon,
  CopyActionIcon,
} from "./action-icons";
import { TooltipIconButton } from "./tooltip-icon-button";
import { Button } from "../../../ui/button";
import { DotMatrix } from "../DotMatrix";
import { Skeleton } from "../../../ui/skeleton";
import { cn } from "./cn";
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
  useThreadViewport,
} from "@assistant-ui/react";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type ComponentType,
  type FC,
  type FormEvent,
  type MouseEvent as ReactMouseEvent,
  type PropsWithChildren,
} from "react";
import { ComposerTriggerPopover } from "./composer-trigger-popover.aui";
import { MessageError } from "./message-error.aui";
import { ComposerBlockCaret } from "./block-caret";
import { ThreadSource } from "./source";
import { TypedWelcomeCopy } from "./typed-welcome-copy";

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
   * The credit line under the composer. The host supplies it so the surface
   * reads as a digithings product; absent means no footer (the package does
   * not own the credit copy).
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
};

const DEFAULT_GROUP_DISCLOSURE: ThreadGroupDisclosure = {
  reasoning: "collapsed",
  toolCalls: "collapsed",
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
              value={{ reasoning: reasoningMode, toolCalls: toolCallsMode }}
            >
              <ThreadRoot
                autoFocus={autoFocus}
                placeholder={placeholder}
                composerLayout={composerLayout}
              />
            </ThreadGroupDisclosureContext.Provider>
          </ThreadComponentsContext.Provider>
        </ThreadActionsContext.Provider>
      </ThreadChromeContext.Provider>
    </HiddenAttachmentNamesProvider>
  );
};

const ThreadRoot: FC<{
  autoFocus: boolean;
  placeholder?: string | undefined;
  composerLayout: ComposerLayout;
}> = ({ autoFocus, placeholder, composerLayout }) => {
  const { Welcome = ThreadWelcome, Footer } =
    useContext(ThreadComponentsContext);
  const { className } = useContext(ThreadChromeContext);

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
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        // The top-anchored message carries `padding-top: 1.5rem` (chat-aui.css)
        // so it does not sit flush against the viewport top. `tallerThan` scores
        // the anchor's offsetHeight, which includes that padding, so it is
        // raised by the same 1.5rem to keep the set of fully-pinned messages
        // unchanged from before the padding was added.
        topAnchorMessageClamp={{ tallerThan: "11.5em", visibleHeight: "6em" }}
        data-slot="aui_thread-viewport"
        className="relative flex flex-1 flex-col overflow-x-hidden overflow-y-scroll scroll-smooth digichat-thread__viewport"
      >
        <div className="mx-auto flex w-full max-w-(--thread-max-width) flex-1 flex-col px-4 pt-4">
          <AuiIf condition={isHistoryLoadingView}>
            <ThreadHistorySkeleton />
          </AuiIf>

          <div
            data-slot="aui_message-group"
            className="mb-14 flex flex-col gap-y-6 empty:hidden"
          >
            <ThreadPrimitive.Messages>
              {() => <ThreadMessage />}
            </ThreadPrimitive.Messages>
          </div>

          <ThreadPrimitive.ViewportFooter className="aui-thread-viewport-footer digichat-thread__footer bg-background sticky bottom-0 mt-auto flex flex-col gap-4 overflow-visible pb-4 md:pb-6">
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
            />
            {Footer ? <Footer /> : null}
          </ThreadPrimitive.ViewportFooter>
        </div>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadMessage: FC = () => {
  const { AssistantMessage: AssistantMessageComponent = AssistantMessage } =
    useContext(ThreadComponentsContext);
  const role = useAuiState((s) => s.message.role);
  const isEditing = useAuiState((s) => s.message.composer.isEditing);

  if (isEditing) return <EditComposer />;
  if (role === "user") return <UserMessage />;
  return <AssistantMessageComponent />;
};

const ThreadScrollToBottom: FC = () => {
  const viewportEl = useThreadViewport((s) => s.element.viewport);
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
      const composer = viewportEl.querySelector<HTMLElement>(
        '[data-slot="aui_composer-shell"]',
      );
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
        <DotMatrix state="scroll" label="Scroll to bottom" className="size-3.5" />
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
          label="Example"
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
            label="Example"
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
}> = ({ autoFocus, placeholder = "Send a message...", layout }) => {
  const compact = layout === "compact";
  const { onComposerSubmit, slash, mention } = useContext(ThreadChromeContext);
  const inputWrapRef = useRef<HTMLDivElement | null>(null);
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
      className="aui-composer-root relative flex w-full flex-col"
      onSubmit={onComposerSubmit}
    >
      <ComposerPrimitive.AttachmentDropzone asChild>
        <div
          data-slot="aui_composer-shell"
          data-layout={layout}
          onMouseDown={handleShellMouseDown}
          className="border-border/60 data-[dragging=true]:border-ring dark:border-muted-foreground/15 flex w-full cursor-text flex-col gap-2 rounded-(--composer-radius) border bg-(--composer-bg) p-(--composer-padding) data-[dragging=true]:border-dashed data-[dragging=true]:bg-[color-mix(in_oklab,var(--color-accent)_50%,var(--color-background))]"
        >
          <ComposerAttachments />
          <div
            className={cn(
              "aui-composer-main",
              compact && "flex min-w-0 items-center gap-1",
            )}
          >
            {compact ? <ComposerAddAttachment /> : null}
            <div
              ref={inputWrapRef}
              className={cn("aui-composer-input-wrap relative min-w-0", compact && "flex-1")}
            >
              <ComposerPrimitive.Input
                placeholder={placeholder}
                className={cn(
                  "aui-composer-input placeholder:text-muted-foreground/60 max-h-48 w-full resize-none overflow-hidden bg-transparent outline-none",
                  compact
                    ? "min-h-7 px-1.5 py-0 text-sm leading-7"
                    : "min-h-[1.375rem] px-2.5 py-0.5 text-base leading-6",
                )}
                rows={1}
                autoFocus={autoFocus}
                submitMode="enter"
                enterKeyHint="send"
                aria-label="Message"
              />
              <ComposerBlockCaret containerRef={inputWrapRef} />
            </div>
            {compact ? <ComposerSendControls /> : null}
          </div>
          {compact ? null : <ComposerAction />}
        </div>
      </ComposerPrimitive.AttachmentDropzone>
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
  const sendRef = useRef<HTMLButtonElement | null>(null);

  // A `type="submit"` button already submits its form on activation, so the
  // click must not also do it: `preventDefault()` suppresses that implicit
  // submission, and the explicit `requestSubmit()` below replaces it with one
  // we control. Without this the form's `submit` fires twice per click, and the
  // free-turn gate mounted on `onSubmit` runs twice — holding or charging the
  // turn more than once.
  const submitComposer = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const form = sendRef.current?.closest("form");
    if (form) {
      form.requestSubmit();
      return;
    }
    aui.composer.send();
  };

  return (
    <div className="aui-composer-send-controls flex shrink-0 items-center gap-1.5">
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
                label="Voice input"
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
                label="Stop dictation"
                className="aui-composer-stop-dictation-icon size-3.5"
              />
            </TooltipIconButton>
          </ComposerPrimitive.StopDictation>
        </AuiIf>
      </AuiIf>
      <AuiIf condition={(s) => !s.thread.isRunning}>
        <TooltipIconButton
          ref={sendRef}
          tooltip="Send (Enter)"
          side="bottom"
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
            label="Send"
            className="aui-composer-send-icon size-3.5"
          />
        </TooltipIconButton>
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
              label="Stop generating"
              className="aui-composer-cancel-icon size-3.5"
            />
          </Button>
        </ComposerPrimitive.Cancel>
      </AuiIf>
    </div>
  );
};

const ComposerAction: FC = () => {
  return (
    <div className="aui-composer-action-wrapper relative flex items-center justify-between">
      <ComposerAddAttachment />
      <ComposerSendControls />
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
  const connecting = useAuiState((s) =>
    s.message.parts.some(
      (part) =>
        part.type === "data" &&
        part.name === "connection" &&
        (part.data as { state?: string } | undefined)?.state === "connecting",
    ),
  );
  if (toolRunning) return null;
  return (
    <span
      data-slot="aui_assistant-message-indicator"
      className="flex items-center gap-2"
    >
      <DotMatrix
        state="loading"
        label="Assistant is working"
        className="size-3.5"
      />
      {connecting ? (
        <span className="text-sm text-muted-foreground">Connecting…</span>
      ) : null}
    </span>
  );
};

const AssistantMessage: FC = () => {
  const {
    ToolFallback: ToolFallbackComponent = ToolFallback,
    ToolGroup,
    ReasoningGroup,
    Source: SourceComponent = ThreadSource,
  } = useContext(ThreadComponentsContext);
  const { reasoning: reasoningMode, toolCalls: toolCallsMode } = useContext(
    ThreadGroupDisclosureContext,
  );

  const ACTION_BAR_PT = "pt-1.5";
  // Keep the action bar inside the contained root's paint box, then cancel its reserved space in flow.
  const ACTION_BAR_HEIGHT = `min-h-7.5 ${ACTION_BAR_PT}`;

  return (
    <MessagePrimitive.Root
      data-slot="aui_assistant-message-root"
      data-role="assistant"
      className="aui-msg fade-in slide-in-from-bottom-1 animate-in relative grid grid-cols-[minmax(0,1fr)] items-start -mb-7.5 pb-7.5 duration-150 [contain-intrinsic-size:auto_200px] [content-visibility:auto]"
    >
      <div
        data-slot="aui_assistant-message-content"
        className="aui-assistant-message-content text-foreground min-w-0 leading-relaxed wrap-break-word"
      >
        <MessagePrimitive.GroupedParts
          groupBy={groupPartByType({
            reasoning: ["group-chainOfThought", "group-reasoning"],
            "tool-call": ["group-chainOfThought", "group-tool"],
            "standalone-tool-call": [],
          })}
        >
          {({ part, children }) => {
            switch (part.type) {
              case "group-chainOfThought":
                return (
                  <div data-slot="aui_chain-of-thought">{children}</div>
                );
              case "group-tool": {
                if (toolCallsMode === "off") return null;
                if (ToolGroup) {
                  return <ToolGroup group={part}>{children}</ToolGroup>;
                }
                const locked = toolCallsMode === "locked_open";
                return (
                  <ToolGroupRoot
                    variant="ghost"
                    defaultOpen={toolCallsMode === "expanded" || locked}
                    streamingOpen={
                      toolCallsMode === "balanced" &&
                      part.status.type === "running"
                    }
                    {...(locked ? { open: true, onOpenChange: () => {} } : {})}
                  >
                    <ToolGroupTrigger
                      count={part.indices.length}
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
                    streaming={running && reasoningMode === "balanced"}
                    defaultOpen={reasoningMode === "expanded" || locked}
                    {...(locked ? { open: true, onOpenChange: () => {} } : {})}
                  >
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
                return part.dataRendererUI;
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
                return <AssistantWorkingIndicator />;
              case "source":
                return <SourceComponent {...part} />;
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
              <DotMatrix state="prev" label="Undo" className="size-3.5" />
            </TooltipIconButton>
          </BranchPickerPrimitive.Previous>
        </AuiIf>
      ) : null}
      <ActionBarPrimitive.Reload asChild>
        <TooltipIconButton tooltip="Redo">
          <DotMatrix state="refresh" label="Redo" className="size-3.5" />
        </TooltipIconButton>
      </ActionBarPrimitive.Reload>
      {feedback ? (
        <>
          <ActionBarPrimitive.FeedbackPositive asChild>
            <TooltipIconButton tooltip="Good response">
              <DotMatrix state="thumbsUp" label="Good response" className="size-3.5" />
            </TooltipIconButton>
          </ActionBarPrimitive.FeedbackPositive>
          <ActionBarPrimitive.FeedbackNegative asChild>
            <TooltipIconButton tooltip="Bad response">
              <DotMatrix state="thumbsDown" label="Bad response" className="size-3.5" />
            </TooltipIconButton>
          </ActionBarPrimitive.FeedbackNegative>
        </>
      ) : null}
      <ActionBarMorePrimitive.Root>
        <ActionBarMorePrimitive.Trigger asChild>
          <TooltipIconButton tooltip="More">
            <DotMatrix state="more" label="More" className="size-3.5" />
          </TooltipIconButton>
        </ActionBarMorePrimitive.Trigger>
        <ActionBarMorePrimitive.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="aui-action-bar-more-content z-[110] min-w-[8rem] overflow-hidden border p-1"
        >
          <ActionBarPrimitive.ExportMarkdown asChild>
            <ActionBarMorePrimitive.Item className="aui-action-bar-more-item flex cursor-pointer items-center gap-2 bg-transparent px-2 py-1.5 outline-none select-none hover:bg-transparent focus:bg-transparent data-highlighted:bg-transparent data-highlighted:text-ink">
              <DotMatrix state="export" label="Export" className="size-3.5" />
              Export as Markdown
            </ActionBarMorePrimitive.Item>
          </ActionBarPrimitive.ExportMarkdown>
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
      className="aui-msg fade-in slide-in-from-bottom-1 animate-in grid grid-cols-[1.25rem_minmax(0,1fr)_1.75rem] items-start gap-x-[0.55rem] gap-y-2 duration-150 [contain-intrinsic-size:auto_200px] [content-visibility:auto]"
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
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-user-action-bar-root flex flex-row items-center"
    >
      <ActionBarPrimitive.Edit asChild>
        <TooltipIconButton tooltip="Edit" className="aui-user-action-edit">
          <DotMatrix state="edit" label="Edit" className="size-3.5" />
        </TooltipIconButton>
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
};

const EditComposer: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_edit-composer-wrapper"
      className="flex flex-col px-2 [contain-intrinsic-size:auto_200px] [content-visibility:auto]"
    >
      <ComposerPrimitive.Root className="aui-edit-composer-root border-border/60 dark:border-muted-foreground/15 flex w-full cursor-text flex-col rounded-(--composer-radius) border bg-(--composer-bg)">
        <ComposerPrimitive.Input
          className="aui-edit-composer-input text-foreground min-h-14 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-base outline-none"
          autoFocus
        />
        <div className="aui-edit-composer-footer mx-2.5 mb-2.5 flex items-center gap-1.5 self-end">
          <ComposerPrimitive.Cancel asChild>
            <Button dress="chat"
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-3.5"
            >
              Cancel
            </Button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <Button dress="chat" size="sm" className="h-8 rounded-full px-3.5">
              Update
            </Button>
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </MessagePrimitive.Root>
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
          <DotMatrix state="prev" label="Previous" className="size-3.5" />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Next">
          <DotMatrix state="next" label="Next" className="size-3.5" />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};
