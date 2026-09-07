'use client';

export const SETTINGS_LOAD_ERROR_MESSAGE = 'Unable to load settings.';

export type SettingsLoadErrorProps = {
  /** Override the shared default copy (e.g. soft-unavailable 503 messaging). */
  message?: string;
  /** Re-triggers the tab hydrate path (e.g. () => void hydrate()). */
  onRetry: () => void;
  /** Optional test id. Defaults to "settings-load-error". */
  testId?: string;
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
}: SettingsLoadErrorProps) {
  return (
    <div
      data-testid={testId}
      role="alert"
      className="flex items-start justify-between gap-4 border border-hair bg-term-bg/40 px-3 py-2"
    >
      <p className="text-sm text-down">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        data-testid={`${testId}-retry`}
        className="shrink-0 border border-hair px-3 py-1.5 text-xs font-medium text-ink hover:bg-ink/[0.04]"
      >
        Retry
      </button>
    </div>
  );
}
