/**
 * DigiThings hero-picker — accessible icon-tab row that swaps a ProductFrame
 * preview below the hero (Graphite "feature picker" pattern; WAI-ARIA "Tabs
 * with Automatic Activation").
 *
 * Markup contract: a `.hero-picker` containing one `[role="tablist"]` of
 * `[role="tab"]` icon buttons (each `aria-controls` -> a panel id) and matching
 * `[role="tabpanel"]` `.hero-picker__panel` regions (each typically wrapping a
 * `.product-frame`). The active tab gets `aria-selected="true"` + `tabindex 0`;
 * inactive panels get the `hidden` attribute.
 *
 * Usage:
 *   import { initHeroPicker } from './hero-picker.js';
 *   initHeroPicker({ selector: '.hero-picker' });
 *
 * Keyboard: ArrowLeft/ArrowRight move focus and activate (roving tabindex),
 * Home/End jump to the first/last tab — same model as code-sample-band.js.
 */
export function initHeroPicker({ selector = '.hero-picker' } = {}) {
  const pickers = document.querySelectorAll(selector);

  pickers.forEach((root) => {
    const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;
    const panels = tabs.map((tab) => {
      const panelId = tab.getAttribute('aria-controls');
      return panelId ? document.getElementById(panelId) : null;
    });

    const activate = (index, focus = true) => {
      tabs.forEach((tab, i) => {
        const active = i === index;
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
        if (panels[i]) panels[i].hidden = !active;
      });
      if (focus) tabs[index].focus();
    };

    tabs.forEach((tab, i) => {
      tab.addEventListener('click', () => activate(i));
      tab.addEventListener('keydown', (e) => {
        let next = null;
        if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = tabs.length - 1;
        if (next !== null) {
          e.preventDefault();
          activate(next);
        }
      });
    });

    // Normalize from the tab marked aria-selected (default first) without
    // stealing focus on page load.
    const initial = tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true');
    activate(initial >= 0 ? initial : 0, false);
  });

  return { stop() {} };
}
