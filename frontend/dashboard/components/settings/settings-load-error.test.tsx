import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import {
  SETTINGS_LOAD_ERROR_MESSAGE,
  SettingsLoadError,
} from './settings-load-error';

describe('SettingsLoadError', () => {
  it('renders shared default copy and Retry', () => {
    const onRetry = vi.fn();
    const html = renderToStaticMarkup(
      createElement(SettingsLoadError, { onRetry }),
    );
    expect(html).toContain('settings-load-error');
    expect(html).toContain(SETTINGS_LOAD_ERROR_MESSAGE);
    expect(html).toContain('Retry');
    expect(html).toContain('settings-load-error-retry');
  });

  it('allows custom soft-unavailable message while keeping Retry', () => {
    const html = renderToStaticMarkup(
      createElement(SettingsLoadError, {
        message: 'Profile backend is temporarily unavailable. Showing empty form.',
        onRetry: () => undefined,
      }),
    );
    expect(html).toContain('temporarily unavailable');
    expect(html).toContain('Retry');
    expect(html).not.toContain(SETTINGS_LOAD_ERROR_MESSAGE);
  });
});
