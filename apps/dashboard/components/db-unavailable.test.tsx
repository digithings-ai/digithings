import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import DbUnavailable from './db-unavailable';

/**
 * Narrow-width contract for the DB gate (#4452).
 *
 * The gate is the dashboard's honesty surface: it tells the operator live data
 * is unavailable and why. A rendered screenshot (not static review) is what
 * first caught the reported 390px defect, so the guard here pins the rendered
 * invariants that keep the gate from clipping its own message:
 *
 *   - the card opts into a fluid width (`w-full` + a `max-w-*` cap), never a
 *     fixed width that cannot contract;
 *   - the title/body are wrap-safe (`break-words`) and carry no truncating
 *     utility (`truncate` / `whitespace-nowrap` / `line-clamp` / `text-ellipsis`).
 *
 * It cannot measure layout (jsdom has none) — the "no horizontal overflow at
 * 390px" half was verified in a real browser; this pins the markup that makes
 * that possible so a regression is caught without a screenshot.
 */
describe('DbUnavailable narrow-width contract', () => {
  const html = renderToStaticMarkup(<DbUnavailable status="unconfigured" />);

  it('states the full title in the unconfigured case', () => {
    expect(html).toContain('Live data is not connected in this build');
  });

  it('is fluid: fills its container up to a max-width cap, never content-sized', () => {
    expect(html).toContain('w-full');
    expect(html).toContain('max-w-md');
  });

  it('is wrap-safe and never ellipsises its own message', () => {
    expect(html).toContain('break-words');
    // Scope to the message elements: the kit Button legitimately carries
    // `whitespace-nowrap` for its own label, which is not the gate's message.
    const title = html.match(/<h3[^>]*class="([^"]*)"/)?.[1] ?? '';
    const body = html.match(/<p[^>]*class="([^"]*)"/)?.[1] ?? '';
    for (const cls of [title, body]) {
      expect(cls).not.toContain('truncate');
      expect(cls).not.toMatch(/whitespace-nowrap|text-ellipsis|line-clamp/);
    }
  });
});
