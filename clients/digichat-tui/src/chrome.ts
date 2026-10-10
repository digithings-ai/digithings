import type { ChatMessage } from "./read";
import { EXAMPLE, EXPAND, EXPANDED, USER_MARK } from "./theme";

export const SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"] as const;

export const LOADING = "Loading conversation";
export const WORKING = "Assistant is working";

export type Tone = "ink" | "soft" | "mute" | "danger";

export type ThreadLine = { text: string; tone: Tone };

export function spinnerFrame(tick: number): string {
  const frame = SPINNER[Math.abs(tick) % SPINNER.length] ?? SPINNER[0];
  return frame;
}

export function clip(text: string, width: number): string {
  if (text.length <= width) return text;
  if (width <= 1) return "…";
  return `${text.slice(0, width - 1)}…`;
}

export function wrap(text: string, width: number): string[] {
  const limit = Math.max(8, width);
  const lines: string[] = [];
  for (const raw of text.split("\n")) {
    let rest = raw;
    if (rest.length === 0) {
      lines.push("");
      continue;
    }
    while (rest.length > limit) {
      let cut = rest.lastIndexOf(" ", limit);
      if (cut < 8) cut = limit;
      lines.push(rest.slice(0, cut));
      rest = rest.slice(cut).trimStart();
    }
    lines.push(rest);
  }
  return lines;
}

/** Blank titles use the thread-list fallback. A missing session is not a row. */
export function sessionTitle(title: string): string {
  const text = title.trim();
  if (!text || text === "—") return "new chat";
  return text;
}

export function historySkeleton(width: number): ThreadLine[] {
  const bar = (frac: number, right: boolean): ThreadLine => {
    const cells = Math.max(4, Math.min(width, Math.floor(width * frac)));
    const body = "░".repeat(cells);
    const text = right ? `${" ".repeat(Math.max(0, width - cells))}${body}` : body;
    return { text, tone: "mute" };
  };
  return [bar(0.4, true), bar(0.9, false), bar(0.7, false), bar(0.32, true), bar(0.8, false)];
}

export function renderMessages(options: {
  messages: readonly ChatMessage[];
  width: number;
  open: readonly string[];
  busy: boolean;
  spinner: string;
  actions: boolean;
}): ThreadLine[] {
  const lines: ThreadLine[] = [];
  const lastUser = [...options.messages].reverse().find((message) => message.role === "user" && !message.tool);
  const lastAssistant = [...options.messages].reverse().find((message) => message.role === "assistant" && !message.tool && message.text);
  options.messages.forEach((message) => {
    if (message.reasoning) {
      const open = options.open.includes(`${message.id}:reasoning`);
      const mark = open ? EXPANDED : EXPAND;
      lines.push({ text: `${mark} Reasoning`, tone: "mute" });
      if (open) {
        for (const line of wrap(message.reasoning, Math.max(8, options.width - 2))) {
          lines.push({ text: `  ${line}`, tone: "soft" });
        }
      }
    }
    if (message.tool) {
      const open = options.open.includes(message.id);
      const running = message.tool.status === "running";
      const mark = running ? options.spinner : open ? EXPANDED : EXPAND;
      const status = message.tool.status && !running ? `  ${message.tool.status}` : "";
      lines.push({ text: `${mark} ${message.tool.name}${status}`, tone: "soft" });
      if (open && message.tool.detail) {
        for (const line of wrap(message.tool.detail, Math.max(8, options.width - 2))) {
          lines.push({ text: `  ${line}`, tone: "mute" });
        }
      }
      if (message.text && message.text !== message.tool.name && message.text !== "—") {
        for (const line of wrap(message.text, Math.max(8, options.width - 2))) {
          lines.push({ text: `  ${line}`, tone: "soft" });
        }
      }
      return;
    }
    const wrapped = wrap(message.text, Math.max(8, options.width - 2));
    if (message.role === "user") {
      lines.push(
        ...wrapped.map((line, index) => ({
          text: index === 0 ? `${USER_MARK} ${line}` : `  ${line}`,
          tone: "ink" as const,
        })),
      );
      if (options.actions && !options.busy && message === lastUser) {
        lines.push({ text: "edit", tone: "mute" });
      }
      return;
    }
    lines.push(...wrapped.map((line) => ({ text: `  ${line}`, tone: "soft" as const })));
    if (options.actions && !options.busy && message === lastAssistant) {
      const stamp = message.at ? `  ${message.at}` : "";
      lines.push({ text: `copy  redo  more${stamp}`, tone: "mute" });
    }
  });
  if (options.busy) {
    lines.push({ text: `${options.spinner} ${WORKING}`, tone: "mute" });
  }
  return lines;
}

export function welcomeLines(shown: string, done: boolean): ThreadLine[] {
  if (!shown && done) return [];
  return [{ text: done ? shown : `${shown}█`, tone: "ink" }];
}

export function suggestionLines(suggestions: readonly string[], width: number): ThreadLine[] {
  return suggestions.filter((prompt) => prompt.trim()).flatMap((prompt) =>
    wrap(prompt.trim(), Math.max(8, width - 2)).map((line, index) => ({
      text: index === 0 ? `${EXAMPLE} ${line}` : `  ${line}`,
      tone: "soft" as const,
    })),
  );
}

/** `## You` / `## digichat`, text turns only. Tool rows stay out of the file. */
export function exportMarkdown(messages: readonly ChatMessage[]): string {
  const blocks: string[] = [];
  for (const message of messages) {
    if (message.tool) continue;
    const body = message.text.trim();
    if (!body || body === "—") continue;
    const heading = message.role === "user" ? "## You" : "## digichat";
    blocks.push(`${heading}\n\n${body}`);
  }
  return blocks.join("\n\n");
}

export function loadingStatus(spinner: string): string {
  return `${spinner} ${LOADING}`;
}

export function attachmentLine(name: string): string {
  return `${name} · file  x`;
}
