'use client';

import { Button, Kbd, SegmentedControl, Switch } from '@digithings/ui/ui';
import { useAppShell, type Density } from '@/components/app-shell-context';
import { useDashboardTheme, type DashboardTheme } from '@/components/theme-provider';

/**
 * Device-local display prefs. Edits the same state as the sidebar account
 * dropdown (theme provider + app shell), so the dropdown is a shortcut, not a
 * second source. Changes apply immediately; there is nothing to save.
 */
export function AppearanceSection() {
  const { theme, setTheme } = useDashboardTheme();
  const { density, setDensity, sidebarDefault, setSidebarDefault, openCommandPalette } =
    useAppShell();

  return (
    <div className="space-y-4" data-testid="settings-appearance">
      <Row label="Theme" hint="Auto follows the operating system.">
        <SegmentedControl<DashboardTheme>
          aria-label="Theme"
          data-testid="appearance-theme"
          value={theme}
          onChange={setTheme}
          options={[
            { value: 'auto', label: 'Auto' },
            { value: 'dark', label: 'Dark' },
            { value: 'light', label: 'Light' },
          ]}
        />
      </Row>
      <Row label="Density" hint="Row height across tables and lists.">
        <SegmentedControl<Density>
          aria-label="Density"
          data-testid="appearance-density"
          value={density}
          onChange={setDensity}
          options={[
            { value: 'compact', label: 'Compact' },
            { value: 'comfortable', label: 'Comfortable' },
          ]}
        />
      </Row>
      <Row label="Collapse sidebar by default" hint="Used when you have not collapsed it by hand.">
        <Switch
          checked={sidebarDefault === 'collapsed'}
          onCheckedChange={(on) => setSidebarDefault(on ? 'collapsed' : 'expanded')}
          aria-label="Collapse sidebar by default"
          data-testid="appearance-sidebar-default"
        />
      </Row>
      {openCommandPalette ? (
        <Row label="Command palette" hint="Jump to any page or setting.">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={openCommandPalette}
            className="gap-2 font-mono text-ink-soft"
            data-testid="appearance-open-palette"
          >
            Open <Kbd>⌘K</Kbd>
          </Button>
        </Row>
      ) : null}
    </div>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border border-hair bg-surface px-3 py-2.5">
      <div className="min-w-0">
        <p className="text-sm text-ink">{label}</p>
        <p className="text-xs text-ink-mute">{hint}</p>
      </div>
      {children}
    </div>
  );
}
