import { expect, test } from "bun:test";
import {
  cardLines,
  center,
  clip,
  doctorRow,
  dotRow,
  heading,
  historyRow,
  menuRows,
  resultRow,
  statusRow,
  toneForDoctor,
  wrap,
} from "./chrome";
import { CURSOR } from "./theme";

test("clip truncates with one ellipsis and leaves short text alone", () => {
  expect(clip("hello world", 5)).toBe("hell…");
  expect(clip("hello", 5)).toBe("hello");
  expect(clip("hello", 1)).toBe("…");
  expect(clip("hello", 0)).toBe("");
});

test("wrap splits on newlines and hard-cuts long runs", () => {
  expect(wrap("line1\nline2", 20)).toEqual(["line1", "line2"]);
  expect(wrap("x".repeat(30), 10)).toEqual(["xxxxxxxxxx", "xxxxxxxxxx", "xxxxxxxxxx"]);
});

test("dotRow fills to the given width", () => {
  const row = dotRow("stt_model", "ggml-base.en", 30);
  expect(row).toBe("stt_model ....... ggml-base.en");
  expect(row.length).toBe(30);
});

test("menuRows marks the selected row with the cursor glyph", () => {
  const rows = menuRows(["Models", "Features"], 1, 20);
  expect(rows[0]?.text.startsWith(CURSOR)).toBe(false);
  expect(rows[0]?.tone).toBe("soft");
  expect(rows[1]?.text.startsWith(CURSOR)).toBe(true);
  expect(rows[1]?.tone).toBe("ink");
});

test("doctor tone maps status to colour", () => {
  expect(toneForDoctor("ok")).toBe("ink");
  expect(toneForDoctor("missing")).toBe("danger");
  expect(toneForDoctor("info")).toBe("mute");
});

test("doctorRow keeps the [status] id prefix", () => {
  const row = doctorRow("missing", "ffmpeg", "not on PATH", 40);
  expect(row.text.startsWith("[missing] ffmpeg")).toBe(true);
  expect(row.tone).toBe("danger");
});

test("resultRow reads ok and not ready", () => {
  expect(resultRow(true, 20)).toEqual({ text: "result: ok", tone: "accent" });
  expect(resultRow(false, 20)).toEqual({ text: "result: not ready", tone: "danger" });
});

test("cardLines draws a box around its body", () => {
  const lines = cardLines("Models", ["stt_model ... ggml-base.en"], 40);
  expect(lines[0]?.text.startsWith("┌─")).toBe(true);
  expect(lines.at(-1)?.text.startsWith("└")).toBe(true);
  expect(lines[1]?.text.startsWith("│")).toBe(true);
});

test("heading and center place text in the middle", () => {
  expect(heading("Models", 20)).toBe(center("— Models —", 20));
  expect(center("ab", 6)).toBe("  ab");
});

test("historyRow marks the selected entry", () => {
  const row = historyRow({ ts: "2026-09-30T12:00:00.000Z", kind: "dict", text: "hello" }, 60, true);
  expect(row.text.startsWith(CURSOR)).toBe(true);
  expect(row.text).toContain("2026-09-30 12:00:00");
  expect(row.text).toContain("hello");
});

test("statusRow spins while busy and flags errors", () => {
  expect(statusRow("recording", 0).tone).toBe("accent");
  expect(statusRow("error", 0).tone).toBe("danger");
  expect(statusRow("idle", 0).tone).toBe("soft");
});
