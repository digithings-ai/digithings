/* ==========================================================================
   @digithings/design — app-shell-terminal
   --------------------------------------------------------------------------
   Claude-Code-style app chrome: collapsible sidebar, main slot, top bar,
   terminal-like input bar, Cmd+K palette, slash command registry.

   Usage:
     import { initAppShell } from '@digithings/design/app-shell-terminal';
     import '@digithings/design/app-shell-terminal/styles.css';

     const shell = initAppShell({
       hostId: 'app',
       title: 'digichat',
       sidebarSlot: '<div>history / settings</div>',
       mainSlot:    '<div>main content</div>',
       slashCommands: registry,  // optional SlashCommandRegistry instance
       onSubmit: (text) => { ... },
     });
   ========================================================================== */

import { SlashCommandRegistry } from './slash-commands.js';

const FOCUSABLE = 'a,button,input,textarea,select,[tabindex]:not([tabindex="-1"])';

function createEl(tag, className) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  return e;
}

export function initAppShell({
  hostId,
  title = 'digithings',
  sidebarSlot = '',
  mainSlot = '',
  slashCommands,
  onSubmit,
} = {}) {
  const host = hostId ? document.getElementById(hostId) : null;
  if (!host) throw new Error(`initAppShell: no host element for "${hostId}"`);

  const prefersReduced = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const registry = slashCommands instanceof SlashCommandRegistry
    ? slashCommands
    : new SlashCommandRegistry();

  // Built-ins — idempotent; won't overwrite if already registered.
  if (!registry.list().some((c) => c.name === 'help')) {
    registry.register('help', {
      description: 'List available slash commands.',
      handler: () => registry.list(),
    });
  }
  if (!registry.list().some((c) => c.name === 'clear')) {
    registry.register('clear', {
      description: 'Clear the input.',
      handler: () => { input.value = ''; },
    });
  }

  host.classList.add('app-shell');
  if (prefersReduced) host.classList.add('app-shell-reduced-motion');
  host.innerHTML = '';

  // ----- Sidebar ---------------------------------------------------------
  const sidebar = createEl('aside', 'app-sidebar');
  sidebar.setAttribute('aria-label', 'App sidebar');
  sidebar.setAttribute('aria-expanded', 'true');
  const sidebarBody = createEl('div', 'app-sidebar-body');
  sidebarBody.innerHTML = sidebarSlot;
  sidebar.appendChild(sidebarBody);

  // ----- Main column -----------------------------------------------------
  const mainCol = createEl('div', 'app-shell-main-col');

  // Top bar
  const topbar = createEl('header', 'app-topbar');
  const titleEl = createEl('span', 'app-topbar-title');
  titleEl.textContent = title;
  const meta = createEl('span', 'app-topbar-meta');
  meta.textContent = 'ready';
  topbar.appendChild(titleEl);
  topbar.appendChild(meta);

  // Main slot
  const main = createEl('main', 'app-main');
  main.innerHTML = mainSlot;

  // Input bar
  const inputBar = createEl('form', 'app-input');
  inputBar.setAttribute('role', 'search');
  const marker = createEl('span', 'app-input-marker');
  marker.textContent = '>';
  const input = document.createElement('textarea');
  input.className = 'app-input-field';
  input.rows = 1;
  input.setAttribute('aria-label', 'Command input');
  input.placeholder = 'Type a message, or / for commands';
  const hint = createEl('span', 'slash-hint');
  const hintKbd = document.createElement('kbd');
  hintKbd.textContent = '⌘K';
  hint.appendChild(hintKbd);
  inputBar.appendChild(marker);
  inputBar.appendChild(input);
  inputBar.appendChild(hint);

  input.addEventListener('input', () => {
    // Auto-grow a few rows.
    input.style.height = 'auto';
    input.style.height = `${Math.min(200, input.scrollHeight)}px`;
  });

  inputBar.addEventListener('submit', (e) => {
    e.preventDefault();
    const value = input.value.trim();
    if (!value) return;
    if (registry.parse(value)) {
      registry.dispatch(value);
    } else if (typeof onSubmit === 'function') {
      onSubmit(value);
    }
    input.value = '';
    input.style.height = 'auto';
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      inputBar.requestSubmit();
    }
  });

  mainCol.appendChild(topbar);
  mainCol.appendChild(main);
  mainCol.appendChild(inputBar);

  host.appendChild(sidebar);
  host.appendChild(mainCol);

  // ----- Sidebar collapse ------------------------------------------------
  let collapsed = false;
  function setCollapsed(v) {
    collapsed = !!v;
    host.classList.toggle('app-shell-sidebar-collapsed', collapsed);
    sidebar.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  }

  // ----- Command palette (Cmd+K) -----------------------------------------
  const palette = createEl('div', 'app-shell-palette');
  palette.setAttribute('role', 'dialog');
  palette.setAttribute('aria-modal', 'true');
  palette.setAttribute('aria-label', 'Command palette');
  palette.hidden = true;
  const paletteInner = createEl('div', 'app-shell-palette-inner');
  const paletteInput = document.createElement('input');
  paletteInput.type = 'text';
  paletteInput.className = 'app-shell-palette-input';
  paletteInput.placeholder = 'Type a command…';
  paletteInput.setAttribute('aria-label', 'Command palette search');
  const paletteList = createEl('ul', 'app-shell-palette-list');
  paletteInner.appendChild(paletteInput);
  paletteInner.appendChild(paletteList);
  palette.appendChild(paletteInner);
  host.appendChild(palette);

  let lastFocused = null;

  function renderPalette(filter = '') {
    const q = filter.trim().toLowerCase();
    const items = registry.list().filter((c) =>
      !q || c.name.toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q)
    );
    paletteList.innerHTML = '';
    items.forEach((c, i) => {
      const li = createEl('li', 'app-shell-palette-item');
      li.tabIndex = 0;
      li.dataset.name = c.name;
      const nameSpan = createEl('span', 'shell-cmd-ref');
      nameSpan.textContent = `/${c.name}`;
      const descSpan = createEl('span', 'app-shell-palette-desc');
      descSpan.textContent = c.description || '';
      li.appendChild(nameSpan);
      li.appendChild(descSpan);
      if (i === 0) li.classList.add('is-active');
      li.addEventListener('click', () => {
        closePalette();
        registry.dispatch(`/${c.name}`);
      });
      li.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          closePalette();
          registry.dispatch(`/${c.name}`);
        }
      });
      paletteList.appendChild(li);
    });
  }

  function openPalette() {
    lastFocused = document.activeElement;
    palette.hidden = false;
    host.classList.add('app-shell-palette-open');
    paletteInput.value = '';
    renderPalette('');
    paletteInput.focus();
  }
  function closePalette() {
    palette.hidden = true;
    host.classList.remove('app-shell-palette-open');
    if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
  }

  paletteInput.addEventListener('input', () => renderPalette(paletteInput.value));
  paletteInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); closePalette(); return; }
    if (e.key === 'Enter') {
      e.preventDefault();
      const first = paletteList.querySelector('.app-shell-palette-item');
      if (first) {
        closePalette();
        registry.dispatch(`/${first.dataset.name}`);
      }
      return;
    }
    // Simple focus trap: forward Tab into list.
    if (e.key === 'Tab' && !e.shiftKey) {
      const first = paletteList.querySelector('.app-shell-palette-item');
      if (first) { e.preventDefault(); first.focus(); }
    }
  });
  palette.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); closePalette(); }
    // Trap focus inside palette
    if (e.key === 'Tab') {
      const focusables = palette.querySelectorAll(FOCUSABLE);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
  });

  // ----- Global shortcuts ------------------------------------------------
  function onKey(e) {
    const meta = e.metaKey || e.ctrlKey;
    if (meta && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (palette.hidden) openPalette(); else closePalette();
      return;
    }
    if (meta && e.key === '/') {
      e.preventDefault();
      setCollapsed(!collapsed);
    }
  }
  document.addEventListener('keydown', onKey);

  return {
    sidebar,
    main,
    input,
    registry,
    setCollapsed,
    toggleSidebar: () => setCollapsed(!collapsed),
    openPalette,
    closePalette,
    destroy() {
      document.removeEventListener('keydown', onKey);
      host.innerHTML = '';
      host.classList.remove(
        'app-shell',
        'app-shell-reduced-motion',
        'app-shell-sidebar-collapsed',
        'app-shell-palette-open',
      );
    },
  };
}

export { SlashCommandRegistry };
