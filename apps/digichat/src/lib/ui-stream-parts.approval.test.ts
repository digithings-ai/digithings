import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import type { ActivitySpan } from "@/lib/chat-activity";
import {
  MCP_META_TOOLS,
  createActivityWriteContext,
  describePendingMcpOperation,
  finishStandardActivity,
  isApprovableMcpTool,
  pendingMcpDecisionFromEvent,
  uiMessagesForUpstream,
  writePendingMcpApproval,
  writeStandardActivity,
  type UiStreamWriter,
} from "./ui-stream-parts";

type Chunk = Record<string, unknown>;

function harness() {
  const chunks: Chunk[] = [];
  const writer: UiStreamWriter = { write: (c) => chunks.push(c as Chunk) };
  return { chunks, writer, ctx: createActivityWriteContext() };
}

const PENDING_EVENT = {
  error: "mcp_call_requires_human_approval",
  pending_id: "a1b2c3d4e5f60718",
  server_id: "atlassian",
  tool: "addOrEditJiraIssueComment",
  target_arguments: ["issueIdOrKey", "comment"],
  message: "Tool addOrEditJiraIssueComment on server atlassian changes remote state.",
};

describe("pending MCP decision — the composer affordance", () => {
  it("test 1: renders an Approve/Deny row naming the concrete operation and its target", () => {
    const { chunks, writer, ctx } = harness();
    const decision = pendingMcpDecisionFromEvent(PENDING_EVENT);
    expect(decision).not.toBeNull();

    const callId = writePendingMcpApproval(writer, ctx, decision!);
    expect(callId).toBeTruthy();

    // The row opens with the *remote* tool, not the generic meta name, and the
    // title names the operation plus the target argument names.
    const start = chunks.find((c) => c.type === "tool-input-start");
    expect(start).toMatchObject({
      type: "tool-input-start",
      toolCallId: callId,
      toolName: "addOrEditJiraIssueComment",
      title: "addOrEditJiraIssueComment on atlassian — target: issueIdOrKey, comment",
    });

    // The approval-request chunk is what flips assistant-ui into
    // `status.type === "requires-action"`, i.e. the existing Approve/Deny card.
    const approval = chunks.find((c) => c.type === "tool-approval-request");
    expect(approval).toEqual({
      type: "tool-approval-request",
      approvalId: "a1b2c3d4e5f60718",
      toolCallId: callId,
      reason: "tool-calls",
    });

    // The held row must survive end-of-stream: settling it would flip the row to
    // an error state and destroy the only review path.
    finishStandardActivity(writer, ctx);
    expect(chunks.filter((c) => c.type === "tool-output-error")).toHaveLength(0);
    expect(ctx.approvalsByToolCallId?.get(callId!)).toBe("a1b2c3d4e5f60718");
  });

  it("test 2 (regression): a non-pending tool call renders exactly as it does today", () => {
    const span: ActivitySpan = {
      operation: "execute_tool",
      status: "completed",
      label: "digivault_get_note",
      toolName: "digivault_get_note",
      toolResult: "ok",
    };
    const before: Chunk[] = [];
    const w: UiStreamWriter = { write: (c) => before.push(c as Chunk) };
    const ctx = createActivityWriteContext();
    writeStandardActivity(w, span, ctx);
    finishStandardActivity(w, ctx);

    // Positive control: this path really does emit tool parts, so the zero below
    // is an absence and not an instrument that cannot output.
    expect(before.filter((c) => c.type === "tool-input-start")).toHaveLength(1);
    expect(before.filter((c) => c.type === "tool-output-available")).toHaveLength(1);
    expect(before.some((c) => c.type === "tool-approval-request")).toBe(false);
    expect(before.some((c) => c.type === "tool-output-error")).toBe(false);
    expect(ctx.approvalsByToolCallId?.size ?? 0).toBe(0);
  });

  it("test 3: a meta-tool decision does not render an approvable confirmation", () => {
    for (const tool of MCP_META_TOOLS) {
      const { chunks, writer, ctx } = harness();
      const decision = pendingMcpDecisionFromEvent({
        ...PENDING_EVENT,
        pending_id: "deadbeefdeadbeef",
        tool,
      });
      expect(decision).not.toBeNull();
      expect(isApprovableMcpTool(tool)).toBe(false);

      const callId = writePendingMcpApproval(writer, ctx, decision!);
      expect(callId).toBeNull();
      // Nothing at all is emitted: no row, and above all no approval request.
      expect(chunks).toHaveLength(0);
      expect(chunks.some((c) => c.type === "tool-approval-request")).toBe(false);
    }

    // Control: the same shape for a real tool DOES render, so the loop above is
    // discriminating and not passing because every decision is rejected.
    expect(isApprovableMcpTool("addOrEditJiraIssueComment")).toBe(true);
    expect(isApprovableMcpTool("createJiraIssue")).toBe(true);
    // Case-insensitive, so a differently-spelled meta tool cannot produce a card.
    expect(isApprovableMcpTool("ExecuteWrite")).toBe(false);
    expect(isApprovableMcpTool(undefined)).toBe(false);
  });

  it("brief fact 1: an approval part is never forwarded upstream", () => {
    const messages = [
      { id: "m1", role: "assistant", parts: [{ type: "text", text: "I need a decision." }] },
      {
        id: "m2",
        role: "assistant",
        parts: [
          { type: "tool-approval-request", toolCallId: "t1", approvalId: "a1" },
          { type: "tool-approval-response", toolCallId: "t1", approvalId: "a1", approved: true },
        ],
      },
    ] as unknown as UIMessage[];
    const upstream = uiMessagesForUpstream(messages);
    for (const m of upstream) {
      expect(m.parts.every((p) => p.type === "text")).toBe(true);
    }
    expect(JSON.stringify(upstream)).not.toContain("approval");
    // Control: the text part did survive, so the filter is not erasing everything.
    expect(JSON.stringify(upstream)).toContain("I need a decision.");
  });

  it("reads only what digigraph reported — no client-side classification", () => {
    // Missing pending_id or tool is not a decision; it is not rendered as one.
    expect(pendingMcpDecisionFromEvent({ tool: "createJiraIssue" })).toBeNull();
    expect(pendingMcpDecisionFromEvent({ pending_id: "abcd" })).toBeNull();
    expect(pendingMcpDecisionFromEvent(undefined)).toBeNull();
    // A payload that happens to carry `tool` but is not a decision does not
    // fabricate one.
    const { chunks, writer, ctx } = harness();
    expect(
      writePendingMcpApproval(
        writer,
        ctx,
        pendingMcpDecisionFromEvent({ pending_id: "cafebabecafebabe", tool: "createJiraIssue" })!
      )
    ).toBeTruthy();
    expect(chunks.find((c) => c.type === "tool-input-start")).toMatchObject({
      title: "createJiraIssue",
    });
  });

  it("names the server and the target digigraph reported", () => {
    expect(
      describePendingMcpOperation({
        pendingId: "x",
        serverId: "atlassian",
        tool: "addOrEditJiraIssueComment",
        targetArguments: ["issueIdOrKey"],
      })
    ).toBe("addOrEditJiraIssueComment on atlassian — target: issueIdOrKey");
    expect(
      describePendingMcpOperation({
        pendingId: "x",
        serverId: "",
        tool: "someTool",
        targetArguments: [],
      })
    ).toBe("someTool");
  });
});
