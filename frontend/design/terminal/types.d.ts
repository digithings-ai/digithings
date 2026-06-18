export type TerminalLineKind = "prompt" | "output" | "comment" | "tool-call";

export interface TerminalLine {
  kind: TerminalLineKind;
  text: string;
  /** Optional language hint for naive post-stream highlighting. */
  lang?: "js" | "ts" | "tsx" | "py" | "sh" | "json";
}

export interface TerminalHandle {
  append(line: TerminalLine): void;
  clear(): void;
  destroy(): void;
}

export interface InitTerminalOptions {
  elementId: string;
  lines: TerminalLine[];
  speed?: "fast" | "normal" | "slow" | number;
  onReady?: () => void;
}

export function initTerminal(opts: InitTerminalOptions): TerminalHandle;
