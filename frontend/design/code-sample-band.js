/**
 * DigiThings code-sample-band — accessible tabbed code snippets (WAI-ARIA
 * "Tabs with Automatic Activation" pattern) with a copy-to-clipboard button
 * on the active panel.
 *
 * Markup contract: a `.code-sample-band` containing one `[role="tablist"]`
 * of `[role="tab"]` buttons (`aria-controls` -> panel id) and matching
 * `[role="tabpanel"]` <pre><code> blocks, plus an optional
 * `.code-sample-band__copy` button.
 *
 * Usage:
 *   import { initCodeSampleBand } from './code-sample-band.js';
 *   initCodeSampleBand({ selector: '.code-sample-band' });
 *
 * Keyboard: ArrowLeft/ArrowRight move focus and activate (roving tabindex),
 * Home/End jump to the first/last tab.
 */
export function initCodeSampleBand({ selector = '.code-sample-band' } = {}) {
  const bands = document.querySelectorAll(selector);

  bands.forEach((root) => {
    const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
    const panels = tabs.map((tab) => document.getElementById(tab.getAttribute('aria-controls')));
    const copyBtn = root.querySelector('.code-sample-band__copy');

    const activate = (index) => {
      tabs.forEach((tab, i) => {
        const active = i === index;
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
        if (panels[i]) panels[i].hidden = !active;
      });
      tabs[index].focus();
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

    if (copyBtn) {
      copyBtn.addEventListener('click', async () => {
        const activeIndex = tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true');
        const code = panels[activeIndex]?.textContent ?? '';
        try {
          await navigator.clipboard.writeText(code);
          copyBtn.classList.add('is-ok');
          copyBtn.textContent = 'copied';
          setTimeout(() => {
            copyBtn.classList.remove('is-ok');
            copyBtn.textContent = 'copy';
          }, 1500);
        } catch {
          // Clipboard API unavailable or denied — no fallback UI needed for a docs snippet.
        }
      });
    }
  });

  return { stop() {} };
}
