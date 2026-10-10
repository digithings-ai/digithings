/**
 * digivoice chrome: pure render helpers.
 *
 * Every function here is a pure string transform. The React layer in app.tsx
 * only paints these lines; the tests in chrome.test.ts pin them. No network,
 * no clock, no spawn.
 */
import { CURSOR } from "./theme";

export const SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"] as const;

export type Tone = "ink" | "soft" | "mute" | "accent" | "danger" | "warn";
export type Line = { text: string; tone: Tone };

export function spinnerFrame(tick: number): string {
  return SPINNER[Math.abs(Math.floor(tick)) % SPINNER.length];
}

/** Truncate to width, ending with a single ellipsis when it does not fit. */
export function clip(text: string, width: number): string {
  if (width <= 0) return "";
  if (text.length <= width) return text;
  if (width === 1) return "…";
  return text.slice(0, width - 1) + "…";
}

/** Split on newlines and wrap each at the last space, else hard-cut. */
export function wrap(text: string, width: number): string[] {
  const limit = Math.max(1, width);
  const out: string[] = [];
  for (const raw of text.split("\n")) {
    if (raw.length <= limit) {
      out.push(raw);
      continue;
    }
    let rest = raw;
    while (rest.length > limit) {
      const window = rest.slice(0, limit);
      const cut = window.lastIndexOf(" ");
      if (cut >= 8) {
        out.push(rest.slice(0, cut));
        rest = rest.slice(cut + 1);
      } else {
        out.push(window);
        rest = rest.slice(limit);
      }
    }
    out.push(rest);
  }
  return out;
}

export function padRight(text: string, width: number): string {
  return text.length >= width ? text : text + " ".repeat(width - text.length);
}

export function center(text: string, width: number): string {
  const pad = Math.max(0, Math.floor((width - text.length) / 2));
  return " ".repeat(pad) + text;
}

/** `key ......... value`, a dotted leader row. The dots never go below one. */
export function dotRow(key: string, value: string, width: number): string {
  const k = clip(key, Math.max(1, width - 3));
  const v = clip(value, Math.max(1, width - k.length - 2));
  const dots = Math.max(1, width - k.length - v.length - 2);
  return `${k} ${".".repeat(dots)} ${v}`;
}

export type Field = { key: string; value: string };

export function fieldRows(fields: Field[], width: number): Line[] {
  return fields.map((f) => ({ text: dotRow(f.key, f.value, width), tone: "ink" as Tone }));
}

/** `— Models —` section heading, centered to the pane width. */
export function heading(title: string, width: number): string {
  return center(`— ${title} —`, width);
}

export function headingLine(title: string, width: number): Line {
  return { text: heading(title, width), tone: "soft" };
}

/** A menu: the selected row is marked with the cursor glyph. */
export function menuRows(items: string[], index: number, width: number): Line[] {
  return items.map((item, i) => {
    const selected = i === index;
    const text = `${selected ? CURSOR : " "} ${clip(item, Math.max(1, width - 2))}`;
    return { text, tone: selected ? "ink" : "soft" };
  });
}

export type DoctorStatus = "ok" | "missing" | "info";

export function toneForDoctor(status: DoctorStatus): Tone {
  if (status === "missing") return "danger";
  if (status === "info") return "mute";
  return "ink";
}

/** `[ok] whisper-cli  /opt/homebrew/bin/whisper-cli` -> a toned row. */
export function doctorRow(status: DoctorStatus, id: string, detail: string, width: number): Line {
  const head = `[${status}] ${id}`;
  const gap = Math.max(1, 14 - head.length);
  return { text: clip(`${head}${" ".repeat(gap)}${detail}`, width), tone: toneForDoctor(status) };
}

export function resultRow(ok: boolean, width: number): Line {
  return { text: clip(`result: ${ok ? "ok" : "not ready"}`, width), tone: ok ? "accent" : "danger" };
}

export type HistoryEntry = { ts: string; kind: string; text: string };

export function historyRow(entry: HistoryEntry, width: number, selected: boolean): Line {
  const mark = selected ? CURSOR : " ";
  const stamp = entry.ts.slice(0, 19).replace("T", " ");
  const head = `${mark} ${entry.kind.padEnd(5)} ${stamp}  `;
  return { text: clip(`${head}${entry.text}`, width), tone: selected ? "ink" : "soft" };
}

/** A left/right box border. Used for the settings and status cards. */
export function cardLines(title: string, body: string[], width: number): Line[] {
  const inner = Math.max(2, width - 2);
  const top = `┌─ ${clip(title, Math.max(1, inner - 4))} ${"─".repeat(Math.max(0, inner - title.length - 4))}┐`;
  const bottom = `└${"─".repeat(inner)}┘`;
  const rows: Line[] = [{ text: clip(top, width), tone: "mute" }];
  for (const line of body) rows.push({ text: clip(`│ ${padRight(clip(line, inner - 2), inner - 2)} │`, width), tone: "ink" });
  rows.push({ text: clip(bottom, width), tone: "mute" });
  return rows;
}

/** One key-hint footer line: `↑↓ move · Enter select · Esc back · q quit`. */
export function keyHints(keys: string[], width: number): Line {
  return { text: clip(keys.join("  ·  "), width), tone: "mute" };
}

export function statusRow(state: string, tick: number): Line {
  if (state === "recording" || state === "transcribing" || state === "rewriting" || state === "loading") {
    return { text: `${spinnerFrame(tick)} ${state}`, tone: "accent" };
  }
  if (state === "error") return { text: `! ${state}`, tone: "danger" };
  return { text: `${BULLET_GLYPH} ${state}`, tone: "soft" };
}

const BULLET_GLYPH = "·";
