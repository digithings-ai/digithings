/* Mockup D — Quant-native data choreography
   Graceful degrade: if this JS fails or is disabled, every visualization
   still renders as a static SVG snapshot from index.html.
   ------------------------------------------------------------------- */

(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // --------------------------------------------------------------
  // Hero typewriter (placeholder only)
  // --------------------------------------------------------------
  const tw = document.getElementById('typewriter');
  if (tw) {
    const lines = [
      'digigraph route "build a mean-reversion strat on tech"',
      'digiquant backtest --strategy=mr_tech --since=2022',
      'digisearch query "10-K filings semiconductors 2025"',
      'digichat --byok --tools=digiquant,digisearch',
    ];
    let li = 0, ci = 0, erasing = false;
    const tick = () => {
      if (reduced) { tw.textContent = lines[0]; return; }
      const cur = lines[li];
      if (!erasing) {
        tw.textContent = cur.slice(0, ci++);
        if (ci > cur.length) { erasing = true; setTimeout(tick, 1600); return; }
      } else {
        tw.textContent = cur.slice(0, ci--);
        if (ci < 0) { erasing = false; ci = 0; li = (li + 1) % lines.length; }
      }
      setTimeout(tick, erasing ? 25 : 45 + Math.random() * 35);
    };
    tick();
  }

  // --------------------------------------------------------------
  // Scroll reveal (IntersectionObserver)
  // --------------------------------------------------------------
  const revealables = document.querySelectorAll('[data-reveal]');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.setAttribute('data-revealed', 'true');
        const kind = e.target.getAttribute('data-reveal');
        if (kind === 'equity') animateEquityCounters(e.target);
        if (kind === 'graph') animatePacket();
        if (kind === 'vec') revealNeighbors();
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.25 });
  revealables.forEach((r) => io.observe(r));

  // --------------------------------------------------------------
  // Hero stat counters
  // --------------------------------------------------------------
  const heroStatObs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      const el = e.target;
      const target = parseFloat(el.dataset.count || '0');
      const suffix = el.dataset.suffix || '';
      if (reduced) { el.textContent = target + suffix; heroStatObs.unobserve(el); return; }
      const dur = 1200;
      const start = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased) + suffix;
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      heroStatObs.unobserve(el);
    });
  }, { threshold: 0.5 });
  document.querySelectorAll('.hstat-v').forEach((el) => heroStatObs.observe(el));

  // --------------------------------------------------------------
  // Equity-panel counters (Sharpe, DD, YTD, Win)
  // --------------------------------------------------------------
  function animateEquityCounters(root) {
    const counters = root.querySelectorAll('[data-counter]');
    counters.forEach((el) => {
      const target = parseFloat(el.dataset.counter);
      const decimals = parseInt(el.dataset.decimals || '0', 10);
      const suffix = el.dataset.suffix || '';
      if (reduced) {
        el.textContent = target.toFixed(decimals) + suffix;
        return;
      }
      const dur = 1600;
      const start = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - p, 3);
        const val = target * eased;
        el.textContent = val.toFixed(decimals) + suffix;
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  // --------------------------------------------------------------
  // Graph packet animation
  // --------------------------------------------------------------
  function animatePacket() {
    if (reduced) return;
    const motion = document.getElementById('packet-motion');
    if (motion && motion.beginElement) {
      try { motion.beginElement(); } catch (_) {}
    }
  }

  // --------------------------------------------------------------
  // Orderbook
  // --------------------------------------------------------------
  const obBids = document.getElementById('ob-bids');
  const obAsks = document.getElementById('ob-asks');
  const obMid  = document.getElementById('ob-mid');
  let mid = 184.22;
  function formatPx(n) { return n.toFixed(2); }
  function formatSz(n) { return n.toFixed(0).padStart(4, ' '); }

  function seedBook() {
    if (!obBids || !obAsks) return;
    const levels = 10;
    obBids.innerHTML = '';
    obAsks.innerHTML = '';
    for (let i = 0; i < levels; i++) {
      const bpx = mid - 0.02 - i * 0.05;
      const apx = mid + 0.02 + i * 0.05;
      const bsz = Math.round(180 - i * 10 + Math.random() * 40);
      const asz = Math.round(170 - i * 8 + Math.random() * 40);
      obBids.insertAdjacentHTML('beforeend', bookRow(bpx, bsz));
      obAsks.insertAdjacentHTML('beforeend', bookRow(apx, asz));
    }
    resizeBars();
  }
  function bookRow(px, sz) {
    return `<li><span class="bar" style="width:${Math.min(100, sz/3)}%"></span><span>${formatPx(px)}</span><span>${formatSz(sz)}</span></li>`;
  }
  function resizeBars() {
    // already handled inline; leave hook for future
  }
  function flickerBook() {
    if (!obBids || !obAsks || reduced) return;
    const pick = (list) => list.children[Math.floor(Math.random() * list.children.length)];
    const jiggle = (li) => {
      if (!li) return;
      const cells = li.querySelectorAll('span');
      if (cells.length < 3) return;
      const curSz = parseInt(cells[2].textContent, 10);
      const next = Math.max(20, curSz + Math.round((Math.random() - 0.5) * 30));
      cells[2].textContent = formatSz(next);
      const bar = cells[0];
      bar.style.width = Math.min(100, next / 3) + '%';
    };
    jiggle(pick(obBids));
    jiggle(pick(obAsks));
    if (obMid) {
      mid += (Math.random() - 0.5) * 0.04;
      obMid.textContent = mid.toFixed(2);
    }
  }
  seedBook();
  if (!reduced) setInterval(flickerBook, 550);

  // --------------------------------------------------------------
  // Vector-space dots (deterministic-ish)
  // --------------------------------------------------------------
  const vecDots = document.getElementById('vec-dots');
  const vecLines = document.getElementById('vec-lines');
  const W = 620, H = 360;
  const qx = 310, qy = 180;
  const dotCount = 56;
  // simple LCG for stability
  let seed = 7919;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) % 2**32; return (seed >>> 0) / 2**32; };

  const dots = [];
  function renderDots() {
    if (!vecDots) return;
    vecDots.innerHTML = '';
    dots.length = 0;
    for (let i = 0; i < dotCount; i++) {
      const x = 30 + rnd() * (W - 60);
      const y = 30 + rnd() * (H - 60);
      const tag = ['dense','sparse','hybrid'][Math.floor(rnd()*3)];
      dots.push({ x, y, tag });
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', y);
      c.setAttribute('r', 2.4);
      c.classList.add('vec-dot');
      c.dataset.tag = tag;
      vecDots.appendChild(c);
    }
  }
  renderDots();

  function distance(a, b) {
    const dx = a.x - b.x, dy = a.y - b.y;
    return Math.sqrt(dx*dx + dy*dy);
  }

  let currentMode = 'dense';
  function revealNeighbors() {
    if (!vecDots || !vecLines) return;
    // Select neighbors by mode
    const pool = dots
      .map((d, i) => ({ d, i, dist: distance(d, { x: qx, y: qy }) }))
      .filter((o) => currentMode === 'hybrid' ? true : o.d.tag === currentMode || currentMode === o.d.tag || rnd() > 0.6)
      .sort((a, b) => a.dist - b.dist)
      .slice(0, currentMode === 'hybrid' ? 10 : 6);

    // Reset
    vecDots.querySelectorAll('.vec-dot').forEach((n) => n.classList.remove('is-neighbor'));
    vecLines.innerHTML = '';

    pool.forEach((o, idx) => {
      const node = vecDots.children[o.i];
      if (node) node.classList.add('is-neighbor');
      const l = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      l.setAttribute('x1', qx); l.setAttribute('y1', qy);
      l.setAttribute('x2', o.d.x); l.setAttribute('y2', o.d.y);
      l.classList.add('vec-line');
      vecLines.appendChild(l);
      // trigger dash animation
      requestAnimationFrame(() => {
        setTimeout(() => l.classList.add('on'), idx * 70);
      });
    });
  }

  // mode card switcher
  document.querySelectorAll('.mode-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.mode-card').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      currentMode = btn.dataset.mode;
      revealNeighbors();
    });
  });

  // --------------------------------------------------------------
  // DigiChat transcript — word-by-word stream
  // --------------------------------------------------------------
  const chatBody = document.getElementById('chat-body');
  const transcript = [
    { role: 'user', meta: 'you · 14:02',
      text: 'Build me a mean-reversion stat-arb on semiconductors and show a 5-year backtest.' },
    { role: 'bot',  meta: 'digigraph · 14:02',
      text: 'Routing to digiquant for backtest, digisearch for factor context.',
      chips: ['tool: digigraph.route', 'tool: digiquant.backtest'] },
    { role: 'bot',  meta: 'digiquant · 14:03',
      text: 'Backtest complete on 2021-01 to 2026-04. Sharpe 1.84, max drawdown -7.2%, annualized 12.6%. Results attached to session.',
      chips: ['atlas: research_cycle#412', 'artifact: backtest_report.json'] },
    { role: 'user', meta: 'you · 14:04',
      text: 'Stream the equity curve and pin the top 3 contributing signals.' },
    { role: 'bot',  meta: 'digichat · 14:04',
      text: 'Streaming. Top signals: pair-spread z-score, sector-neutral carry, 10d mean-reversion bias. Local keys only — nothing left the box.',
      chips: ['hermes: signal.top3', 'byok: local'] },
  ];

  function streamInto(msgEl, text, done) {
    if (reduced) { msgEl.textContent = text; done && done(); return; }
    const words = text.split(/(\s+)/);
    let i = 0;
    const tick = () => {
      if (i >= words.length) { done && done(); return; }
      msgEl.append(words[i++]);
      setTimeout(tick, 40 + Math.random() * 40);
    };
    tick();
  }

  function buildMsg(m, onDone) {
    const wrap = document.createElement('div');
    wrap.className = 'msg ' + (m.role === 'user' ? 'user' : 'bot');
    const meta = document.createElement('div');
    meta.className = 'msg-meta';
    meta.textContent = m.meta;
    wrap.appendChild(meta);
    const body = document.createElement('div');
    wrap.appendChild(body);
    chatBody.appendChild(wrap);
    streamInto(body, m.text, () => {
      if (m.chips) {
        m.chips.forEach((c) => {
          const chip = document.createElement('span');
          chip.className = 'chip';
          chip.textContent = (c.startsWith('tool:') ? '🔧 ' : c.startsWith('byok') ? '🔑 ' : '✳ ') + c;
          wrap.appendChild(chip);
        });
      }
      chatBody.scrollTop = chatBody.scrollHeight;
      onDone && onDone();
    });
  }

  let chatStarted = false;
  const chatObs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting || chatStarted) return;
      chatStarted = true;
      let idx = 0;
      const next = () => {
        if (idx >= transcript.length) return;
        buildMsg(transcript[idx++], () => setTimeout(next, 450));
      };
      next();
      chatObs.disconnect();
    });
  }, { threshold: 0.3 });
  if (chatBody) chatObs.observe(chatBody);

  // --------------------------------------------------------------
  // Ecosystem toggles
  // --------------------------------------------------------------
  document.querySelectorAll('.eco-tog').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.eco-tog').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      const target = btn.dataset.eco;
      document.querySelectorAll('.eco-overlay').forEach((o) => {
        o.classList.toggle('is-active', o.dataset.layer === target);
      });
    });
  });
  // init active overlay
  const initialEco = document.querySelector('.eco-tog.is-active');
  if (initialEco) {
    const layer = initialEco.dataset.eco;
    document.querySelectorAll('.eco-overlay').forEach((o) => {
      o.classList.toggle('is-active', o.dataset.layer === layer);
    });
  }

  // --------------------------------------------------------------
  // Ticker strip
  // --------------------------------------------------------------
  const tickerTrack = document.getElementById('ticker-track');
  if (tickerTrack) {
    // fictional symbols only — no real companies
    const syms = [
      ['QNT',  210.42], ['ATLS', 84.15], ['HRMS', 42.98], ['KRS',  17.33],
      ['ORCH', 58.21],  ['MCP',  31.07], ['GRPH', 64.90], ['SRCH', 12.55],
      ['NDX-Δ',2341.1], ['USDX', 104.2], ['VOL-X',13.88], ['OIL-S',71.44],
      ['FX-EU',1.0821], ['FX-JP',151.22],['BND-5Y',4.12], ['BND-10',4.38],
    ];
    const mkCell = ([s, p]) => {
      const drift = (Math.random() - 0.5) * 1.2;
      const dir = drift >= 0 ? '▲' : '▼';
      const cls = drift >= 0 ? 't-up' : 't-dn';
      return `<span><span class="t-sym">${s}</span><span class="t-px">${p.toFixed(2)}</span> <span class="${cls}">${dir} ${Math.abs(drift).toFixed(2)}</span></span>`;
    };
    const row = syms.map(mkCell).join('');
    // duplicate for seamless loop
    tickerTrack.innerHTML = row + row;
  }
})();
