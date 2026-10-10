/**
 * digivoice setup shell on the shared TUI foundation.
 *
 * Left: the setup menu (same labels as `digivoice setup --print`). Right: the
 * screen for the selected item. Every value is read from the digivoice CLI; an
 * edit is a `settings set`. A live status strip reads `digivoice status`.
 * TUI-first, no web app.
 */
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DigivoiceWordmark, WORDMARK_ROWS } from "./wordmark";
import { ACCENT, BG, CURSOR, DANGER, HAIR, INK, MUTE, SOFT, WARN } from "./theme";
import {
  type Line,
  type Tone,
  cardLines,
  center,
  clip,
  doctorRow,
  dotRow,
  headingLine,
  keyHints,
  menuRows,
  resultRow,
  spinnerFrame,
  statusRow,
} from "./chrome";
import {
  INITIAL_UI,
  type KeyCtx,
  type KeyEffect,
  type Row,
  type Screen,
  type UiState,
  reduceKey,
} from "./keys";
import {
  DASH,
  type DoctorReport,
  type History,
  type SetupPayload,
  type StatusSnapshot,
  readDoctor,
  readHistory,
  readSetup,
  readStatus,
  saveSetting,
} from "./read";

const TONE: Record<Tone, string> = { ink: INK, soft: SOFT, mute: MUTE, accent: ACCENT, danger: DANGER, warn: WARN };

const MENU_FALLBACK = [
  "Models (STT / TTS / rewrite)",
  "Features (paste, banner)",
  "Hotkeys (docs)",
  "Hardware recommendations (#4939 hook)",
  "Review & save",
  "Doctor (run health checks)",
  "Quit",
];

const MODEL_FALLBACK = [
  "stt_model",
  "tts_voice",
  "rewrite_enabled",
  "rewrite_preset",
  "rewrite_model",
  "rewrite_runner",
  "rewrite_auto_route",
  "rewrite_timeout_seconds",
];
const FEATURE_FALLBACK = ["paste_on_stop", "live_banner", "banner_position", "banner_density", "banner_animations"];

const BOOL_KEYS = new Set(["rewrite_enabled", "rewrite_auto_route", "paste_on_stop", "live_banner", "banner_animations"]);
const CYCLE_KEYS = new Set(["banner_position", "banner_density", "rewrite_preset", "rewrite_runner"]);
const CYCLES: Record<string, string[]> = {
  banner_position: ["top-center", "top-left", "top-right", "bottom-center", "bottom-left", "bottom-right", "center"],
  banner_density: ["mini", "peek", "full"],
  rewrite_preset: ["none", "email", "sms", "professional", "coding", "blog"],
  rewrite_runner: ["auto", "ollama", "llama.cpp"],
};

const CREDIT = "digivoice · local speech · stays on this machine";

function fmtValue(value: unknown): string {
  if (value === null || value === undefined) return "(unset)";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value.length ? value : DASH;
  if (Array.isArray(value)) return value.length ? value.join(", ") : DASH;
  return JSON.stringify(value);
}

function screenTitle(screen: Screen): string {
  switch (screen) {
    case "models":
      return "Models";
    case "features":
      return "Features";
    case "hotkeys":
      return "Hotkeys";
    case "hardware":
      return "Hardware recommendations";
    case "review":
      return "Review & save";
    case "doctor":
      return "Doctor";
    case "history":
      return "History";
    default:
      return "digivoice setup";
  }
}

export function App() {
  const renderer = useRenderer();
  const { width, height } = useTerminalDimensions();

  const [ui, setUi] = useState<UiState>(INITIAL_UI);
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [status, setStatus] = useState<StatusSnapshot | null>(null);
  const [note, setNote] = useState("");
  const [tick, setTick] = useState(0);
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  const uiRef = useRef(ui);
  const setupRef = useRef(setup);
  const editKeyRef = useRef(editKey);
  const editDraftRef = useRef(editDraft);
  uiRef.current = ui;
  setupRef.current = setup;
  editKeyRef.current = editKey;
  editDraftRef.current = editDraft;

  const reload = useCallback(async () => {
    const next = await readSetup();
    if (next) setSetup(next);
    else setNote("digivoice CLI not reachable");
    return next;
  }, []);

  useEffect(() => {
    void reload();
    const statusTimer = setInterval(() => {
      void readStatus().then(setStatus);
    }, 1500);
    return () => clearInterval(statusTimer);
  }, [reload]);

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 80);
    return () => clearInterval(timer);
  }, []);

  const menu = setup?.setup_menu?.length ? setup.setup_menu : MENU_FALLBACK;
  const modelFields = setup?.model_fields?.length ? setup.model_fields : MODEL_FALLBACK;
  const featureFields = setup?.feature_fields?.length ? setup.feature_fields : FEATURE_FALLBACK;

  const rows: Row[] = useMemo(() => {
    const edit = (id: string): Row => ({ id, kind: BOOL_KEYS.has(id) ? "toggle" : CYCLE_KEYS.has(id) ? "cycle" : "edit" });
    switch (ui.screen) {
      case "models":
        return [...modelFields.map(edit), { id: "back", kind: "back" }];
      case "features":
        return [...featureFields.map(edit), { id: "back", kind: "back" }];
      case "doctor":
        return [
          { id: "doctor", kind: "read" },
          { id: "back", kind: "back" },
        ];
      default:
        return [{ id: "back", kind: "back" }];
    }
  }, [ui.screen, modelFields, featureFields]);

  const ctx: KeyCtx = useMemo(() => ({ menu, rows }), [menu, rows]);

  const openScreen = useCallback(
    async (screen: Screen) => {
      if (screen === "doctor") {
        const report = await readDoctor();
        setDoctor(report);
        if (!report) setNote("doctor did not answer");
      }
      if (screen === "history") {
        const hist = await readHistory(undefined, 50);
        setHistory(hist);
        if (!hist) setNote("history did not answer");
      }
      if (screen === "review") void reload();
    },
    [reload],
  );

  const runEffect = useCallback(
    (effect: KeyEffect | null) => {
      if (!effect) return;
      switch (effect.type) {
        case "quit":
          renderer.destroy();
          break;
        case "open":
          void openScreen(effect.screen);
          break;
        case "reload":
          void reload().then((next) => setNote(next ? "reloaded" : "digivoice CLI not reachable"));
          break;
        case "edit":
          setEditKey(effect.id);
          setEditDraft(fmtValue(setupRef.current?.settings?.[effect.id]));
          setNote("");
          break;
        case "toggle": {
          const current = setupRef.current?.settings?.[effect.id];
          const next = current === true ? "false" : "true";
          void saveSetting(effect.id, next).then((ok) => {
            setNote(ok ? `${effect.id} = ${next}` : `${effect.id} not saved`);
            void reload();
          });
          break;
        }
        case "cycle": {
          const key = effect.id;
          const options = CYCLES[key] ?? [];
          const current = String(setupRef.current?.settings?.[key] ?? "");
          const at = options.indexOf(current);
          const next = options.length ? options[(((at < 0 ? 0 : at) + effect.delta) % options.length + options.length) % options.length] : current;
          void saveSetting(key, next).then((ok) => {
            setNote(ok ? `${key} = ${next}` : `${key} not saved`);
            void reload();
          });
          break;
        }
        case "read":
          void openScreen("doctor");
          break;
        default:
          break;
      }
    },
    [renderer, reload, openScreen],
  );

  const commitEdit = useCallback(async () => {
    const key = editKeyRef.current;
    if (!key) return;
    const value = editDraftRef.current;
    const ok = await saveSetting(key, value);
    setEditKey(null);
    setNote(ok ? `${key} = ${value}` : `${key} not saved`);
    void reload();
  }, [reload]);

  const onKey = useRef<(key: { name?: string; ctrl?: boolean; sequence?: string }) => void>(() => {});
  onKey.current = (key) => {
    const name = key.name ?? "";
    if (editKeyRef.current) {
      if (name === "escape") {
        setEditKey(null);
        setNote("");
        return;
      }
      if (name === "return" || name === "enter") {
        void commitEdit();
        return;
      }
      if (name === "backspace") {
        setEditDraft((d) => d.slice(0, -1));
        return;
      }
      const ch = key.sequence && key.sequence.length === 1 ? key.sequence : name.length === 1 ? name : "";
      if (ch.length === 1 && ch >= " ") setEditDraft((d) => d + ch);
      return;
    }
    const result = reduceKey(uiRef.current, key, ctx);
    uiRef.current = result.state;
    setUi(result.state);
    if (result.effect?.type === "back") setNote("");
    runEffect(result.effect);
  };
  useKeyboard((key) => onKey.current(key));

  const rail = Math.min(34, Math.max(22, Math.floor(width * 0.3)));
  const pane = Math.max(8, width - rail - 4);
  const wordmarkRows = WORDMARK_ROWS;
  const bodyHeight = Math.max(6, height - wordmarkRows - 5);

  const toneOf = (t: Tone) => TONE[t];
  const Row = ({ line, selected }: { line: Line; selected: boolean }) => (
    <text fg={selected ? toneOf("accent") : toneOf(line.tone)}>{clip(line.text, pane)}</text>
  );

  const settings = setup?.settings ?? {};
  const menuLines = menuRows(menu, ui.menuIndex, rail - 2);
  const content: Line[] = [];

  if (ui.screen === "home") {
    const paths = setup?.paths;
    content.push(...cardLines("digivoice", [
      "DigiVoice · local speech config",
      paths ? `settings: ${paths.settings_file}` : "settings: (digivoice not reachable)",
      paths ? `data: ${paths.data_dir}` : "data: —",
    ], pane));
    content.push({ text: "", tone: "ink" });
    content.push(headingLine("Live status", pane));
    const st = status?.state ?? (setup ? "idle" : "unreachable");
    content.push(statusRow(st, tick));
    if (status?.text) content.push({ text: `  ${status.text}`, tone: "soft" });
    content.push({ text: "", tone: "ink" });
    content.push(headingLine("Hardware", pane));
    content.push({ text: `  ${setup?.hardware.pointer ?? "see epic #4939 / CHR-853"}`, tone: "mute" });
    for (const tier of setup?.hardware.tiers ?? []) content.push({ text: `  ${tier.tier}: ${tier.model} — ${tier.note}`, tone: "soft" });
  } else if (ui.screen === "models" || ui.screen === "features") {
    const keys = ui.screen === "models" ? modelFields : featureFields;
    const body = keys.map((k) => dotRow(k, fmtValue(settings[k]), Math.max(8, pane - 4)));
    content.push(...cardLines(screenTitle(ui.screen), body, pane));
    content.push({ text: "", tone: "ink" });
    content.push(headingLine("Actions", pane));
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const label = row.kind === "back" ? "Back" : row.kind === "toggle" ? `Toggle ${row.id}` : row.kind === "cycle" ? `Cycle ${row.id}` : `Edit ${row.id}`;
      const selected = ui.rowIndex === i;
      content.push({ text: `${selected ? CURSOR : " "} ${label}`, tone: selected ? "accent" : "soft" });
    }
  } else if (ui.screen === "hotkeys") {
    const hk = setup?.hotkeys;
    const body = hk
      ? [`dict_toggle ${".".repeat(6)} ${hk.dict_toggle}`, `speak_selection ${".".repeat(2)} ${hk.speak_selection}`, `cancel ${".".repeat(11)} ${hk.cancel}`]
      : ["digivoice not reachable"];
    content.push(...cardLines("Hotkeys (read-only docs)", body, pane));
    content.push({ text: "", tone: "ink" });
    content.push({ text: "  Hotkeys live in digivoice/hammerspoon/, not the package.", tone: "mute" });
  } else if (ui.screen === "hardware") {
    content.push(headingLine("Hardware recommendations", pane));
    content.push({ text: `  ${setup?.hardware.pointer ?? "See epic #4939 / CHR-853 — catalog not rebuilt here."}`, tone: "soft" });
    content.push({ text: "", tone: "ink" });
    for (const tier of setup?.hardware.tiers ?? []) {
      content.push({ text: `  ${tier.tier.padEnd(8)} ${tier.model}`, tone: "ink" });
      content.push({ text: `  ${" ".repeat(8)} ${tier.note}`, tone: "mute" });
    }
    content.push({ text: "", tone: "ink" });
    content.push(keyHints(["Esc back", "q quit"], pane));
  } else if (ui.screen === "review") {
    content.push(headingLine("Review & save", pane));
    content.push({ text: "  Every change is written with `settings set` as you make it.", tone: "mute" });
    content.push({ text: "", tone: "ink" });
    for (const [k, v] of Object.entries(settings)) {
      content.push({ text: `  ${k} ${".".repeat(Math.max(1, 26 - k.length))} ${fmtValue(v)}`, tone: "ink" });
    }
  } else if (ui.screen === "doctor") {
    content.push(headingLine("Doctor", pane));
    if (doctor) {
      for (const check of doctor.checks) content.push(doctorRow(check.status, check.id, check.detail, pane));
      content.push({ text: "", tone: "ink" });
      content.push(resultRow(doctor.ok, pane));
    } else {
      content.push({ text: "  running digivoice doctor…", tone: "soft" });
    }
  } else if (ui.screen === "history") {
    content.push(headingLine("History", pane));
    if (history && history.entries.length) {
      content.push({ text: `  ${history.count} of ${history.total} entries · ${history.file}`, tone: "mute" });
      content.push({ text: "", tone: "ink" });
      for (const entry of history.entries.slice(-Math.max(1, bodyHeight - 4))) {
        content.push({ text: clip(`  ${entry.ts.slice(0, 19).replace("T", " ")}  ${entry.kind.padEnd(5)}  ${entry.text}`, pane), tone: "soft" });
      }
    } else {
      content.push({ text: "  no history file yet.", tone: "mute" });
    }
  }

  const statusState = status?.state ?? (setup ? "idle" : "unreachable");
  const statusLine = statusRow(statusState, tick);
  const editing = editKey !== null;

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <DigivoiceWordmark cols={width} />

      <box height={1} flexDirection="row" backgroundColor={BG} paddingLeft={2} paddingRight={2}>
        <text fg={INK}>{clip(`digivoice setup`, Math.floor(pane / 2))}</text>
        <text fg={MUTE}>{clip(`  ${setup ? "local" : "digivoice CLI not reachable"}  ${setup?.paths.data_dir ?? ""}`, pane)}</text>
      </box>

      <box flexGrow={1} flexDirection="row" backgroundColor={BG}>
        <box width={rail} flexDirection="column" backgroundColor={BG} border={["right"]} borderColor={HAIR} paddingLeft={1}>
          <text fg={MUTE}>{clip("setup", rail - 2)}</text>
          {menuLines.map((line, i) => (
            <text key={i} fg={ui.screen === "home" && i === ui.menuIndex ? ACCENT : toneOf(line.tone)}>
              {clip(line.text, rail - 2)}
            </text>
          ))}
          <box flexGrow={1} />
          <text fg={MUTE}>{clip(`${spinnerFrame(tick)} ${statusState}`, rail - 2)}</text>
        </box>

        <box flexGrow={1} flexDirection="column" backgroundColor={BG} paddingLeft={2} paddingRight={2} paddingTop={1} overflow="hidden">
          {content.slice(0, bodyHeight).map((line, i) => (
            <Row key={i} line={line} selected={false} />
          ))}
        </box>
      </box>

      <box height={1} flexDirection="row" backgroundColor={BG} paddingLeft={2} paddingRight={2}>
        <text fg={editing ? ACCENT : toneOf(statusLine.tone)}>
          {clip(editing ? `edit ${editKey} = ${editDraft}█` : `${statusLine.text}${note ? `  ·  ${note}` : ""}`, pane + rail)}
        </text>
      </box>
      <box height={1} flexDirection="row" backgroundColor={BG} paddingLeft={2} paddingRight={2}>
        <text fg={MUTE}>
          {clip(
            editing
              ? "Enter save  ·  Esc cancel"
              : ui.screen === "home"
                ? "↑↓ move  ·  Enter select  ·  Esc back  ·  q quit"
                : "↑↓ move  ·  Enter act  ·  ←→ cycle  ·  Esc back  ·  h history  ·  q quit",
            pane + rail,
          )}
        </text>
      </box>
      <box height={2} flexDirection="column" backgroundColor={BG} border={["top"]} borderColor={HAIR} paddingLeft={2} paddingRight={2}>
        <text fg={MUTE}>{clip(center(CREDIT, width - 4), width - 4)}</text>
      </box>
    </box>
  );
}
