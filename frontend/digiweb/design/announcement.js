/**
 * DigiThings announcement-bar — Graphite-style 48px full-width notice above the
 * nav, content-gated. Renders ONLY when handed enabled content, so it is OFF by
 * default: empty / `{ enabled: false }` / missing text → nothing is rendered.
 * When `href` is set the whole bar is the link (a stretched-link overlay); the
 * optional dismiss button sits above the overlay and persists a per-`id`
 * dismissal in localStorage. No slide-in animation (reduced-motion friendly by
 * design — there is no motion to suppress).
 *
 * Content shape: `{ enabled, id?, text, href?, linkLabel? }` — see
 * site/README.md and ./announcement-example.json.
 *
 * Usage:
 *   import { initAnnouncement } from './announcement.js';
 *   initAnnouncement({ selector: '#announcement', data: cfg });
 *   // or fetch it:
 *   //   fetch('/announcement.json').then((r) => r.json())
 *   //     .then((data) => initAnnouncement({ data }));
 */
import { escapeHtml } from './html-escape.js';

// Allow only navigational URL shapes — relative paths, fragments, and
// http(s)/mailto. Rejects javascript:/data: (and other) schemes so a stray
// config value can't smuggle a script URL into the bar's href. Returns "" for
// anything unsafe, which the caller treats as "no link".
function safeHref(href) {
  if (typeof href !== 'string') return '';
  const v = href.trim();
  if (/^(\/|#|\.\/|\.\.\/|https?:\/\/|mailto:)/i.test(v)) return v;
  return '';
}

export function initAnnouncement({
  selector = '#announcement',
  data = null,
  storageKey = 'dt-announcement-dismissed',
} = {}) {
  const host = document.querySelector(selector);
  if (!host) return { stop() {} };

  const hide = () => {
    host.hidden = true;
    host.innerHTML = '';
  };

  // Content gate: no data, disabled, or empty text → render nothing.
  if (!data || data.enabled === false || !data.text) {
    hide();
    return { stop() {} };
  }

  // Respect a prior per-id dismissal.
  try {
    if (data.id && localStorage.getItem(storageKey) === String(data.id)) {
      hide();
      return { stop() {} };
    }
  } catch {
    // localStorage unavailable (private mode / disabled) — just show the bar.
  }

  const href = safeHref(data.href);
  const hasLink = Boolean(href);
  host.hidden = false;
  host.className = `announcement${hasLink ? ' announcement--link' : ''}`;
  host.setAttribute('role', 'region');
  host.setAttribute('aria-label', 'Announcement');

  const link = hasLink
    ? `<a class="announcement__link" href="${escapeHtml(href)}">${
        escapeHtml(data.linkLabel || 'Learn more')
      } <span aria-hidden="true">&rarr;</span></a>`
    : '';

  host.innerHTML = `
    <span class="announcement__text"><span>${escapeHtml(data.text)}</span>${link}</span>
    <button class="announcement__dismiss" type="button" aria-label="Dismiss announcement">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
    </button>`;

  host.querySelector('.announcement__dismiss').addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    hide();
    try {
      if (data.id) localStorage.setItem(storageKey, String(data.id));
    } catch {
      // Persisting the dismissal is best-effort; the bar is already hidden.
    }
  });

  return { stop() {} };
}
