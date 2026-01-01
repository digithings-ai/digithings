/** One plural message: `{count}` is replaced by the formatted number. */
export type PluralMessage = Partial<Record<Intl.LDMLPluralRule, string>> & { other: string };

/**
 * Every static string the chat trace (reasoning, tool calls, the grouped
 * summary line, status tags) shows. One table per language under `locales/`;
 * adding a language means adding one table and registering it in `index.tsx`.
 * Tool names and model text are not here: they stay as they come.
 */
export type TraceStrings = {
  reasoning: string;
  thinking: string;
  thought: string;
  working: string;
  worked: string;
  /** `{tool}` is the running tool's name. */
  workingOn: string;
  toolFallbackName: string;
  needsInput: string;
  stopped: string;
  failed: string;
  usedTools: PluralMessage;
  thoughtAndUsedTools: PluralMessage;
  toolCalls: PluralMessage;
  usedTool: string;
  cancelledTool: string;
  failedTool: string;
  runningTool: string;
  waitingOnTool: string;
  errorPrefix: string;
  cancelledPrefix: string;
};

export type TraceStringKey = { [K in keyof TraceStrings]: TraceStrings[K] extends string ? K : never }[keyof TraceStrings];
export type TracePluralKey = { [K in keyof TraceStrings]: TraceStrings[K] extends PluralMessage ? K : never }[keyof TraceStrings];
