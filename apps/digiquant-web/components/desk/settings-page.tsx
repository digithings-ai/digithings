"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { SegmentedControl } from "@digithings/ui/ui";
import {
  applyDocumentTheme,
  matchThemeStep,
  readThemeState,
  themeCycle,
} from "@digithings/ui/theme";
import { deskHomeHref } from "./desk-manifest";
import { useDeskAccess } from "./desk-access";
import {
  CHAT_MODELS,
  DENSITIES,
  NOTIFY_MODES,
  REFRESH_SECONDS,
  STALE_SESSIONS,
  type AppSettings,
  type DensityName,
  type NotifyMode,
  type RefreshSec,
  type StaleSessions,
} from "./app-settings";
import { useAppSettings, writeSettings } from "./app-settings-store";

const LABEL = "m-0 text-[0.6875rem] tracking-[0.04em] text-ink-mute";

const themeListeners = new Set<() => void>();

function subscribeDocumentTheme(onStoreChange: () => void): () => void {
  themeListeners.add(onStoreChange);
  return () => {
    themeListeners.delete(onStoreChange);
  };
}

function documentThemeStepId(): string {
  const painted = readThemeState();
  return matchThemeStep(painted.preference, painted.palette, painted.resolved).id;
}

function serverThemeStepId(): string {
  return "default:dark";
}

function publishDocumentTheme(): void {
  for (const listener of themeListeners) listener();
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border border-hair bg-surface px-3 py-3">
      <h2 className="m-0 font-mono text-[0.6875rem] font-normal tracking-[0.04em] text-ink-mute">{title}</h2>
      {children}
    </section>
  );
}

function refreshLabel(seconds: RefreshSec): string {
  if (seconds === 0) return "Off";
  if (seconds === 120) return "2m";
  return `${seconds}s`;
}

/** Editable desk preferences. Each control writes the saved document and the app reads it back. */
export function SettingsPage({ path }: { path: string }) {
  const settings = useAppSettings();
  const { manifest, setDesk } = useDeskAccess();
  const router = useRouter();
  const desks = (manifest?.desks ?? []).filter((desk) => desk.access === "granted");
  const currentId = useSyncExternalStore(
    subscribeDocumentTheme,
    documentThemeStepId,
    serverThemeStepId,
  );

  const patch = (partial: Partial<AppSettings>) => {
    writeSettings({ ...settings, ...partial });
  };

  const chooseDesk = (id: string) => {
    const next = desks.find((desk) => desk.id === id);
    patch({ defaultDesk: id });
    setDesk(id);
    const href = next ? deskHomeHref(next) : null;
    if (href) router.push(href);
  };

  return (
    <form
      data-settings-page=""
      data-density-choice={settings.density}
      data-refresh={settings.refreshSec}
      data-stale={settings.staleSessions}
      data-notify={settings.notify}
      data-chat-model={settings.chatModel}
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-3 py-3"
      onSubmit={(event) => event.preventDefault()}
    >
      <header className="flex flex-col gap-1">
        <h2 className="m-0 font-mono text-[0.75rem] font-normal tracking-[0.04em] text-ink">Settings</h2>
        <p className="m-0 font-mono text-[0.75rem] leading-[1.45] text-ink-mute">
          {path === "/fx/settings"
            ? "These choices apply on the FX desk and the rest of the app."
            : "Choices here are saved in this browser and take effect immediately."}
        </p>
      </header>

      <Section title="Desk">
        {desks.length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className={LABEL}>Default desk</p>
            <SegmentedControl
              aria-label="Default desk"
              className="flex-wrap"
              value={settings.defaultDesk ?? ""}
              options={desks.map((desk) => ({ value: desk.id, label: desk.label }))}
              onChange={chooseDesk}
            />
          </div>
        ) : (
          <p className="m-0 font-mono text-[0.75rem] text-ink-mute">Default desk loads with the app. Your saved desk is used when the list arrives.</p>
        )}
      </Section>

      <Section title="Appearance">
        <div className="flex flex-col gap-1">
          <p className={LABEL}>Theme</p>
          <SegmentedControl
            aria-label="Theme"
            className="flex-wrap"
            value={currentId}
            options={themeCycle().map((step) => ({ value: step.id, label: step.label }))}
            onChange={(id) => {
              const step = themeCycle().find((item) => item.id === id);
              if (!step) return;
              applyDocumentTheme(step.mode, step.palette);
              publishDocumentTheme();
            }}
          />
        </div>
        <div className="flex flex-col gap-1">
          <p className={LABEL}>Density</p>
          <SegmentedControl
            aria-label="Density"
            value={settings.density}
            options={DENSITIES.map((density) => ({ value: density, label: density }))}
            onChange={(density: DensityName) => patch({ density })}
          />
        </div>
      </Section>

      <Section title="Data">
        <div className="flex flex-col gap-1">
          <p className={LABEL}>Refresh</p>
          <SegmentedControl
            aria-label="Refresh interval"
            className="flex-wrap"
            value={String(settings.refreshSec)}
            options={REFRESH_SECONDS.map((seconds) => ({ value: String(seconds), label: refreshLabel(seconds) }))}
            onChange={(value) => patch({ refreshSec: Number(value) as RefreshSec })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <p className={LABEL}>Stale after</p>
          <SegmentedControl
            aria-label="Stale threshold"
            value={String(settings.staleSessions)}
            options={STALE_SESSIONS.map((sessions) => ({
              value: String(sessions),
              label: sessions === 1 ? "1 session" : `${sessions} sessions`,
            }))}
            onChange={(value) => patch({ staleSessions: Number(value) as StaleSessions })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <p className={LABEL}>Stale notice</p>
          <SegmentedControl
            aria-label="Stale notice"
            value={settings.notify}
            options={NOTIFY_MODES.map((mode) => ({ value: mode, label: mode === "off" ? "Off" : "Banner" }))}
            onChange={(notify: NotifyMode) => patch({ notify })}
          />
        </div>
      </Section>

      <Section title="digichat">
        <div className="flex flex-col gap-1">
          <p className={LABEL}>Model</p>
          <SegmentedControl
            aria-label="Chat model"
            className="flex-wrap"
            value={settings.chatModel}
            options={CHAT_MODELS.map((model) => ({ value: model, label: model }))}
            onChange={(chatModel) => patch({ chatModel })}
          />
        </div>
      </Section>
    </form>
  );
}
