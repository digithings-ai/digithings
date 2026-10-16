"use client";

import { useState } from "react";

import {
  Button,
  Label,
  Select,
  SelectItem,
  SelectPopup,
  SelectTrigger,
  SelectValue,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@digithings/ui/ui";

/**
 * Settings — preference rows in one card, plus the tab-visibility rule: a lower
 * plan never sees Custom+ tabs (they are omitted, not greyed). Danger zone last.
 *
 * Wave 1: every tab strip is the stock kit Tabs — the theme row and the two
 * plan-visibility strips are panel-less tabs (they select, they do not reveal
 * content). The old toggle/segment/select/tabs dress is gone; the danger
 * action is the stock destructive Button.
 * Wave 4: the Switch, the Select (kit `SelectPopup`, popup renders in place
 * inside the panel, no portal; the kit item renders its own check), and the
 * module `<label>` (now kit Label) moved off the controls layer onto
 * `@digithings/ui/ui`.
 */

type Theme = "system" | "light" | "dark";

const THEMES: { value: Theme; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const MODULES = ["digiquant", "digigraph", "digisearch", "digivault"];

const CUSTOM_TABS = ["Profile", "Pipeline", "Keys", "Brokers", "Notifications", "Billing", "About"];

const OBSERVER_TABS = ["Notifications", "Billing", "About"];

export function SettingsPanel() {
  const [digests, setDigests] = useState(true);
  const [telemetry, setTelemetry] = useState(false);
  const [theme, setTheme] = useState<Theme>("system");

  return (
    <section className="section-block">
      <p className="kicker">{"// settings"}</p>
      <h2 className="title">Every switch in one column.</h2>
      <p className="section-copy">
        Grouped rows inside a single card: label and consequence on the left, control on the right,
        a hairline between each decision. The danger zone sits at the bottom behind one more
        hairline — red is reserved for it.
      </p>

      <div className="mt-[1.2rem] rounded-none border border-hair bg-surface">
        <div className="acct-setting-row">
          <div>
            <p className="block text-[0.88rem] text-ink" id="setting-digests">
              Email digests
            </p>
            <p className="acct-setting-desc">Weekly PnL and drift summary, Mondays 07:00.</p>
          </div>
          <Switch
            checked={digests}
            aria-labelledby="setting-digests"
            onCheckedChange={setDigests}
          />
        </div>

        <div className="acct-setting-row">
          <div>
            <p className="block text-[0.88rem] text-ink" id="setting-telemetry">
              Usage telemetry
            </p>
            <p className="acct-setting-desc">Anonymous counters only — never strategy payloads.</p>
          </div>
          <Switch
            checked={telemetry}
            aria-labelledby="setting-telemetry"
            onCheckedChange={setTelemetry}
          />
        </div>

        <div className="acct-setting-row">
          <div>
            <p className="block text-[0.88rem] text-ink" id="setting-theme">
              Theme
            </p>
            <p className="acct-setting-desc">Follows the OS unless pinned.</p>
          </div>
          <Tabs value={theme} onValueChange={(value) => setTheme(value as Theme)}>
            <TabsList aria-labelledby="setting-theme">
              {THEMES.map((option) => (
                <TabsTrigger key={option.value} value={option.value}>
                  {option.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="acct-setting-row">
          <div>
            <Label className="block text-[0.88rem] text-ink" htmlFor="setting-module">
              Default module
            </Label>
            <p className="acct-setting-desc">Where new sessions open.</p>
          </div>
          <Select defaultValue="digiquant">
            <SelectTrigger id="setting-module">
              <SelectValue />
            </SelectTrigger>
            <SelectPopup>
              {MODULES.map((module) => (
                <SelectItem key={module} value={module}>
                  {module}
                </SelectItem>
              ))}
            </SelectPopup>
          </Select>
        </div>

        <Tabs defaultValue={CUSTOM_TABS[0]} className="px-[1.1rem] pt-4">
          <TabsList aria-label="Settings (custom plan)">
            {CUSTOM_TABS.map((label) => (
              <TabsTrigger key={label} value={label}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <p className="acct-setting-tab-note">
          Custom+ sees every tab. Observer (free) never sees Profile, Pipeline, Keys, or Brokers —
          those controls are omitted, not greyed out.
        </p>
        <Tabs defaultValue={OBSERVER_TABS[0]} className="px-[1.1rem] pt-4">
          <TabsList aria-label="Settings (observer plan)">
            {OBSERVER_TABS.map((label) => (
              <TabsTrigger key={label} value={label}>
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="acct-danger">
          <div>
            <p className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-danger">danger zone</p>
            <p className="acct-setting-desc">
              Deletes every strategy, backtest, and API key in this workspace. No undo.
            </p>
          </div>
          <Button type="button" variant="destructive">
            Delete workspace
          </Button>
        </div>
      </div>
    </section>
  );
}
