"use client";

import type { ComponentType, FC, PropsWithChildren, ReactNode } from "react";
import {
  MessagePrimitive,
  useAuiState,
  type ToolCallMessagePartComponent,
} from "@assistant-ui/react";
import {
  Reasoning,
  ReasoningContent,
  ReasoningRoot,
  ReasoningText,
  ReasoningTrigger,
} from "../aui-default/reasoning.aui";
import { ToolFallback } from "../aui-default/tool-fallback.aui";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "../aui-default/tool-group.aui";
import { WorkChain } from "./work-chain";
import {
  chainFollowedByText,
  chainGroupBy,
  chainHoldsWork,
  chainToolCount,
  reasoningGroupDisclosure,
  toolGroupDisclosure,
  useDeployWorkDisclosure,
} from "../../../trace-grouping";
import { useViewDisclosure } from "../../../stock/deploy-ui-context";

export type AssistantTraceGroupPart = MessagePrimitive.GroupedParts.GroupPart;

type GroupedPartsRender = Parameters<
  NonNullable<MessagePrimitive.GroupedParts.Props["children"]>
>[0];

/** A part the trace does not own (text, file, image, indicator, data, source). */
export type AssistantTracePartProps = {
  part: GroupedPartsRender["part"];
  children: ReactNode;
};

export type AssistantTraceProps = {
  /**
   * Renders the parts that are not the trace (text, file, image, indicator,
   * data, source). Return `null` to drop a part.
   */
  renderPart: (props: AssistantTracePartProps) => ReactNode;
  /** Replaces assistant-ui's tool card for calls with no registered tool UI. */
  ToolFallback?: ToolCallMessagePartComponent | undefined;
  /** Replaces the `N tool calls` group. */
  ToolGroup?:
    | ComponentType<PropsWithChildren<{ group: AssistantTraceGroupPart }>>
    | undefined;
  /** Replaces the reasoning box. */
  ReasoningGroup?:
    | ComponentType<PropsWithChildren<{ group: AssistantTraceGroupPart }>>
    | undefined;
};

/**
 * The assistant message trace the base skin draws: one work chain over the
 * reasoning and tool calls (folded it reads "Used 3 tools"), a reasoning box
 * and an `N tool calls` group inside it, and assistant-ui's own tool card for
 * each call. The grouping and fold rules are the shared trace rules
 * (`../../../trace-grouping`, the digichat skin's); the look is assistant-ui's
 * defaults (`../aui-default`). Shared by the base skin and the stock thread so
 * both trace the same way; each skin keeps its own text, file and indicator
 * rendering through `renderPart`.
 */
export const AssistantTrace: FC<AssistantTraceProps> = ({
  renderPart,
  ToolFallback: ToolFallbackComponent = ToolFallback,
  ToolGroup,
  ReasoningGroup,
}) => {
  const disclosure = useViewDisclosure();
  const { reasoningMode, toolCallsMode, disclosure: work } = useDeployWorkDisclosure();
  // The whole turn, not just the group: the tools answer faster than the
  // chain can fold, and a group that closes between two of them flickers.
  const turnRunning = useAuiState((s) => s.thread.isRunning);
  const messageParts = useAuiState((s) => s.message.parts);

  return (
    <MessagePrimitive.GroupedParts groupBy={chainGroupBy}>
      {({ part, children }) => {
        switch (part.type) {
          case "group-chainOfThought":
            // A chain of only status or source parts is not work: no
            // header, the loading row covers that phase. The parts still
            // render bare so a backend notice does not vanish.
            if (!chainHoldsWork(messageParts, part.indices)) return <>{children}</>;
            // One header for the whole chain: the reasoning and the tool
            // calls collapse together.
            return (
              <div data-slot="aui_chain-of-thought">
                <WorkChain
                  key={disclosure.key}
                  indices={part.indices}
                  openAtRest={work.openAtRest}
                  foldOnAnswer={work.foldOnAnswer}
                  followedByText={chainFollowedByText(messageParts, part.indices)}
                >
                  {children}
                </WorkChain>
              </div>
            );
          case "group-tool": {
            if (toolCallsMode === "off") return null;
            // The group can hold the source and status parts between two
            // tool runs; the count is the tool calls only.
            const toolCount = chainToolCount(messageParts, part.indices);
            if (toolCount === 0) return <div data-slot="aui_chain-tools">{children}</div>;
            if (ToolGroup) return <ToolGroup group={part}>{children}</ToolGroup>;
            const running = part.status.type === "running";
            const group = toolGroupDisclosure(work, toolCallsMode, running || turnRunning);
            return (
              <ToolGroupRoot
                key={disclosure.key}
                variant="ghost"
                defaultOpen={group.defaultOpen}
                streamingOpen={group.streamingOpen}
                {...(group.locked ? { open: true, onOpenChange: () => {} } : {})}
              >
                <ToolGroupTrigger count={toolCount} active={running} disabled={group.locked} />
                <ToolGroupContent>{children}</ToolGroupContent>
              </ToolGroupRoot>
            );
          }
          case "group-reasoning": {
            if (reasoningMode === "off") return null;
            if (ReasoningGroup) return <ReasoningGroup group={part}>{children}</ReasoningGroup>;
            const running = part.status.type === "running";
            const box = reasoningGroupDisclosure(work, reasoningMode, running || turnRunning);
            return (
              <ReasoningRoot
                key={disclosure.key}
                variant="ghost"
                className="mb-0"
                streaming={box.streamingOpen}
                defaultOpen={box.defaultOpen}
                {...(box.locked ? { open: true, onOpenChange: () => {} } : {})}
              >
                {/* The reasoning is a sub-step with its own disclosure
                    inside the chain, streaming while it runs. */}
                <ReasoningTrigger active={running} disabled={box.locked} />
                <ReasoningContent aria-busy={running}>
                  <ReasoningText>{children}</ReasoningText>
                </ReasoningContent>
              </ReasoningRoot>
            );
          }
          case "reasoning":
            if (reasoningMode === "off") return null;
            return <Reasoning {...part} />;
          case "tool-call":
            if (toolCallsMode === "off") return null;
            // assistant-ui's ToolFallback owns the approval controls too.
            return part.toolUI ?? <ToolFallbackComponent key={disclosure.key} {...part} />;
          default:
            return renderPart({ part, children });
        }
      }}
    </MessagePrimitive.GroupedParts>
  );
};
