"use client";

import {
  ComposerAddAttachment,
  ComposerAttachments,
  UserMessageAttachments,
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
import { ToolFallback } from "./tool-fallback.aui";
import {
  CheckActionIcon,
  CopyActionIcon,
} from "./action-icons";
import { TooltipIconButton } from "./tooltip-icon-button";
import { Button } from "./ui/button";
import { DotMatrix } from "../DotMatrix";
import { Skeleton } from "./ui/skeleton";
import { cn } from "./cn";
import {
  ActionBarMorePrimitive,
  ActionBarPrimitive,
  AuiIf,
  type AssistantState,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  groupPartByType,
  MessagePrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  type FileMessagePartComponent,
  type ImageMessagePartComponent,
  type ToolCallMessagePartComponent,
  type Unstable_DirectiveFormatter,
  type Unstable_TriggerItem,
  type Unstable_TriggerMatcher,
  useAuiState,
} from "@assistant-ui/react";
import {
  createContext,
  useContext,
  type ComponentType,
  type FC,
  type FormEvent,
  type PropsWithChildren,
} from "react";
import { ComposerTriggerPopover } from "./composer-trigger-popover.aui";

export type ThreadGroupPart = MessagePrimitive.GroupedParts.GroupPart;

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
  className?: string | undefined;
  /** Embed send-gate / system page-context attach. */
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  /**
   * Native assistant-ui slash adapter (`unstable_useSlashCommandAdapter`).
   * Mounted on compact embed/modal composers only.
   */
  slash?: ThreadSlashTrigger | undefined;
};

/** `{ adapter, action }` from `unstable_useSlashCommandAdapter`. */
export type ThreadSlashTrigger = {
  adapter: {
    categories(): readonly unknown[];
    categoryItems(categoryId: string): readonly Unstable_TriggerItem[];
    search?(query: string): readonly Unstable_TriggerItem[];
  };
  action: {
    onExecute: (item: Unstable_TriggerItem) => void;
    removeOnExecute?: boolean;
    formatter?: Unstable_DirectiveFormatter;
  };
  iconMap?: Record<string, FC<{ className?: string }>>;
  matcher?: Unstable_TriggerMatcher;
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

type ThreadChrome = {
  welcome: string;
  welcomeBody: readonly string[];
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  className?: string;
  slash?: ThreadSlashTrigger;
};

const DEFAULT_CHROME: ThreadChrome = {
  welcome: "How can I help you today?",
  welcomeBody: [],
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
    <Skeleton className="ml-auto h-9 w-2/5 rounded-xl motion-reduce:animate-none" />
    <div className="flex flex-col gap-y-2">
      <Skeleton className="h-4 w-11/12 motion-reduce:animate-none" />
      <Skeleton className="h-4 w-4/5 motion-reduce:animate-none" />
      <Skeleton className="h-4 w-3/5 motion-reduce:animate-none" />
    </div>
    <Skeleton className="ml-auto h-9 w-1/3 rounded-xl motion-reduce:animate-none" />
    <div className="flex flex-col gap-y-2">
      <Skeleton className="h-4 w-10/12 motion-reduce:animate-none" />
      <Skeleton className="h-4 w-2/3 motion-reduce:animate-none" />
    </div>
  </div>
);

export const Thread: FC<ThreadProps> = ({
  components = EMPTY_COMPONENTS,
  autoFocus = true,
  placeholder,
  composerLayout = "expanded",
  actions,
  welcome,
  welcomeBody,
  className,
  onComposerSubmit,
  slash,
}) => {
  const resolvedActions: Required<ThreadActions> = {
    undo: actions?.undo !== false,
    feedback: actions?.feedback === true,
  };
  const chrome: ThreadChrome = {
    welcome: welcome ?? DEFAULT_CHROME.welcome,
    welcomeBody: welcomeBody ?? DEFAULT_CHROME.welcomeBody,
    onComposerSubmit,
    className,
    slash,
  };
  return (
    <ThreadChromeContext.Provider value={chrome}>
      <ThreadActionsContext.Provider value={resolvedActions}>
        <ThreadComponentsContext.Provider value={components}>
          <ThreadRoot
            autoFocus={autoFocus}
            placeholder={placeholder}
            composerLayout={composerLayout}
          />
        </ThreadComponentsContext.Provider>
      </ThreadActionsContext.Provider>
    </ThreadChromeContext.Provider>
  );
};

const ThreadRoot: FC<{
  autoFocus: boolean;
  placeholder?: string | undefined;
  composerLayout: ComposerLayout;
}> = ({ autoFocus, placeholder, composerLayout }) => {
  const { Welcome = ThreadWelcome } = useContext(ThreadComponentsContext);
  const { className } = useContext(ThreadChromeContext);

  return (
    <ThreadPrimitive.Root
      className={cn(
        "aui-root aui-thread-root digichat-thread bg-background @container flex h-full flex-col",
        className,
      )}
      data-user-align="left"
      style={{
        ["--thread-max-width" as string]: "44rem",
        ["--composer-bg" as string]: "var(--color-card)",
        ["--composer-radius" as string]: "0",
        ["--composer-padding" as string]: "8px",
      }}
    >
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        data-slot="aui_thread-viewport"
        className="relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth digichat-thread__viewport"
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
      className="aui-thread-welcome-root flex flex-col items-start text-left"
    >
      <h1 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in fill-mode-both text-2xl font-medium tracking-tight duration-200">
        {welcome}
      </h1>
      {welcomeBody.map((line) => (
        <p key={line} className="aui-thread-welcome-copy">
          {line}
        </p>
      ))}
    </div>
  );
};

const ThreadSuggestions: FC = () => {
  return (
    <div className="aui-thread-welcome-suggestions flex w-full flex-col items-stretch gap-0.5">
      <ThreadPrimitive.Suggestions>
        {() => <ThreadSuggestionItem />}
      </ThreadPrimitive.Suggestions>
    </div>
  );
};

const ThreadSuggestionItem: FC = () => {
  return (
    <SuggestionPrimitive.Trigger send asChild>
      <button
        type="button"
        className="aui-thread-welcome-suggestion fade-in slide-in-from-bottom-1 animate-in fill-mode-both grid w-full cursor-pointer grid-cols-[1.25rem_minmax(0,1fr)] items-start gap-x-[0.55rem] rounded-none border-0 bg-transparent px-0 py-0.5 text-left text-sm font-normal duration-200"
      >
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
  const { onComposerSubmit, slash } = useContext(ThreadChromeContext);
  const bar = (
    <ComposerPrimitive.Root
      className="aui-composer-root relative flex w-full flex-col"
      onSubmit={onComposerSubmit}
    >
      <ComposerPrimitive.AttachmentDropzone asChild>
        <div
          data-slot="aui_composer-shell"
          data-layout={layout}
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
            <ComposerPrimitive.Input
              placeholder={placeholder}
              className={cn(
                "aui-composer-input placeholder:text-muted-foreground/60 max-h-48 w-full resize-none overflow-hidden bg-transparent outline-none",
                compact
                  ? "min-h-7 flex-1 px-1.5 py-0 text-sm leading-7"
                  : "min-h-[1.375rem] px-2.5 py-0.5 text-base leading-6",
              )}
              rows={1}
              autoFocus={autoFocus}
              submitMode="enter"
              enterKeyHint="send"
              aria-label="Message"
            />
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
    </ComposerPrimitive.Root>
  );
  if (!slash) return bar;
  return (
    <ComposerPrimitive.Unstable_TriggerPopoverRoot>
      {bar}
    </ComposerPrimitive.Unstable_TriggerPopoverRoot>
  );
};

const ComposerSendControls: FC = () => {
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
        <ComposerPrimitive.Send asChild>
          <TooltipIconButton
            tooltip="Send (Enter)"
            side="bottom"
            type="button"
            variant="ghost"
            size="icon"
            className="aui-composer-send size-7 rounded-full"
            aria-label="Send message"
          >
            <DotMatrix
              state="send"
              label="Send"
              className="aui-composer-send-icon size-3.5"
            />
          </TooltipIconButton>
        </ComposerPrimitive.Send>
      </AuiIf>
      <AuiIf condition={(s) => s.thread.isRunning}>
        <ComposerPrimitive.Cancel asChild>
          <Button
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

const MessageError: FC = () => {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 flex items-start gap-2 text-sm">
        <DotMatrix state="error" label="Error" />
        <ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};

/** Thread-level cubes only when no tool is already animating its own matrix. */
const AssistantWorkingIndicator: FC = () => {
  const toolRunning = useAuiState((s) =>
    s.message.parts.some(
      (part) => part.type === "tool-call" && part.status.type === "running",
    ),
  );
  if (toolRunning) return null;
  return (
    <span data-slot="aui_assistant-message-indicator">
      <DotMatrix
        state="loading"
        label="Assistant is working"
        className="size-3.5"
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
                return <div data-slot="aui_chain-of-thought">{children}</div>;
              case "group-tool":
                if (ToolGroup) {
                  return <ToolGroup group={part}>{children}</ToolGroup>;
                }
                return <div data-slot="aui_tool-chain">{children}</div>;
              case "group-reasoning": {
                if (ReasoningGroup) {
                  return (
                    <ReasoningGroup group={part}>{children}</ReasoningGroup>
                  );
                }
                const running = part.status.type === "running";
                return (
                  <ReasoningRoot variant="ghost" streaming={running}>
                    <ReasoningTrigger active={running} />
                    <ReasoningContent aria-busy={running}>
                      <ReasoningText>{children}</ReasoningText>
                    </ReasoningContent>
                  </ReasoningRoot>
                );
              }
              case "text":
                return <MarkdownText />;
              case "reasoning":
                return <Reasoning {...part} />;
              case "tool-call":
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
        <BranchPicker />
        <AssistantActionBar />
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
    </ActionBarPrimitive.Root>
  );
};

const UserFilePart: FileMessagePartComponent = (part) => (
  <div data-slot="aui_user-message-file" className="py-1">
    <File {...part} />
  </div>
);

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
            <Button
              variant="ghost"
              size="sm"
              className="h-8 rounded-full px-3.5"
            >
              Cancel
            </Button>
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send asChild>
            <Button size="sm" className="h-8 rounded-full px-3.5">
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
