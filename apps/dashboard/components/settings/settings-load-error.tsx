'use client';

import { Alert, AlertDescription, Button } from '@digithings/ui/ui';

export const SETTINGS_LOAD_ERROR_MESSAGE = 'Unable to load settings.';

export type SettingsLoadErrorProps = {
  /** Override the shared default copy (e.g. soft-unavailable 503 messaging). */
  message?: string;
  /** Re-triggers the tab hydrate path (e.g. () => void hydrate()). */
  onRetry: () => void;
  /** Optional test id. Defaults to "settings-load-error". */
  testId?: string;
  /** Visual tone: error (default, text-down) or soft (text-warn). */
  tone?: 'error' | 'soft';
};

/**
 * Shared Settings fetch/error shell (CHR-3675 Approach A).
 *
 * Hard hydrate failures across Profile, Pipeline, Keys, Brokers, Notifications,
 * and About (RemainingHopStatus) share one copy + Retry. Validation, save, and
 * action errors stay local to each tab. NOT_READY / 503 soft-unavailable copy
 * may pass a custom `message` but still renders through this shell so Retry
 * stays consistent. Mirrors the SnapshotErrorBanner Retry UX.
 */
export function SettingsLoadError({
  message = SETTINGS_LOAD_ERROR_MESSAGE,
  onRetry,
  testId = 'settings-load-error',
  tone = 'error',
}: SettingsLoadErrorProps) {
  const soft = tone === 'soft';
  return (
    <Alert
      data-testid={testId}
      className={`flex items-start justify-between gap-4 bg-term-bg/40 px-3 py-2 ${
        soft ? 'border-warn/40' : 'border-down/40'
      }`}
    >
      <AlertDescription className={`text-sm ${soft ? 'text-warn' : 'text-down'}`}>
        {message}
      </AlertDescription>
      <Button
        type="button"
        variant="outline"
        onClick={onRetry}
        data-testid={`${testId}-retry`}
        className="h-auto shrink-0 border-hair px-3 py-1.5 text-xs text-ink"
      >
        Retry
      </Button>
    </Alert>
  );
}
