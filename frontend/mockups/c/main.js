/* Mockup C — Terminal-forward
   ------------------------------------------------------------------
   - Hero typewriter that cycles through 3 example queries.
   - Pane switcher (tabs + j/k/g/G keys).
   - Ecosystem sub-terminals animate in sequence when pane visible.
   - Honors prefers-reduced-motion (instant content, no typewriter). */

(() => {
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ------------------------------------------------------ pane routing */
  const tabs  = Array.from(document.querySelectorAll('.tab'));
  const panes = Array.from(document.querySelectorAll('.pane'));
  const order = ['hero', 'act1', 'act2', 'act3', 'act4', 'act5'];
  let current = 'hero';

  function show(id) {
    if (id === current) return;
    const from = document.querySelector(`.pane[data-pane="${current}"]`);
    const to   = document.querySelector(`.pane[data-pane="${id}"]`);
    if (!to) return;

    if (!prefersReduced && from) {
      from.classList.add('is-leaving');
      setTimeout(() => {
        from.classList.remove('is-active', 'is-leaving');
        from.setAttribute('aria-hidden', 'true');
      }, 380);
    } else if (from) {
      from.classList.remove('is-active');
      from.setAttribute('aria-hidden', 'true');
    }

    to.setAttribute('aria-hidden', 'false');
    to.classList.add('is-active');
    if (!prefersReduced) {
      to.classList.add('is-entering');
      setTimeout(() => to.classList.remove('is-entering'), 520);
    }

    tabs.forEach(t => t.classList.toggle('is-active', t.dataset.tab === id));
    current = id;

    // Kick off pane-specific content
    if (id === 'act5') runEcosystem();

    // Smooth scroll to top of stage on mobile
    window.scrollTo({ top: 0, behavior: prefersReduced ? 'auto' : 'smooth' });
  }

  tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.tab)));

  document.addEventListener('keydown', (e) => {
    if (['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) return;
    const i = order.indexOf(current);
    if (e.key === 'j' || e.key === 'ArrowDown')  { e.preventDefault(); show(order[Math.min(order.length-1, i+1)]); }
    else if (e.key === 'k' || e.key === 'ArrowUp'){ e.preventDefault(); show(order[Math.max(0, i-1)]); }
    else if (e.key === 'g')                        { show(order[0]); }
    else if (e.key === 'G')                        { show(order[order.length-1]); }
  });

  /* ------------------------------------------------------ typewriter */
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function rand(a,b) { return a + Math.random() * (b-a); }

  async function typeInto(el, text, cursorEl) {
    if (prefersReduced) { el.textContent = text; return; }
    el.textContent = '';
    for (const ch of text) {
      el.textContent += ch;
      // variable speed: spaces faster, punctuation briefly pauses
      let d = rand(20, 60);
      if (ch === ' ') d = rand(10, 30);
      if ('.?!,'.includes(ch)) d += 120;
      await sleep(d);
    }
  }

  async function printLines(el, lines, perLine=60) {
    el.hidden = false;
    if (prefersReduced) {
      el.innerHTML = lines.join('\n');
      return;
    }
    el.innerHTML = '';
    for (const line of lines) {
      const div = document.createElement('div');
      el.appendChild(div);
      // Render raw HTML line instantly (so span colors appear), then pause.
      div.innerHTML = line;
      await sleep(perLine);
    }
  }

  // Hero state
  const heroLine1 = document.getElementById('heroLine1');
  const heroLine2 = document.getElementById('heroLine2');
  const heroBoot  = document.getElementById('heroBoot');
  const heroAnswer= document.getElementById('heroAnswer');
  const typedInit = heroLine1.querySelector('[data-typed-target="init"]');
  const typedQuery= heroLine2.querySelector('[data-typed-target="query"]');
  const cursor1 = heroLine1.querySelector('.cursor');
  const cursor2 = heroLine2.querySelector('.cursor');

  const queries = [
    {
      q: 'What does DigiGraph do?',
      a: [
        '<span class="info">digigraph</span> → orchestration brain',
        '  <span class="dim">∟</span> routes requests through a LangGraph supervisor',
        '  <span class="dim">∟</span> discovers tools via MCP registry (builtins + verticals)',
        '  <span class="dim">∟</span> exposes an <span class="ok">OpenAI-compatible</span> surface',
      ],
    },
    {
      q: 'Run a mean-reversion backtest on tech.',
      a: [
        '<span class="info">digiquant/atlas</span> → loading strategy <span class="ok">mean_reversion_v3</span>',
        '  lookback=20  z_entry=2.0  z_exit=0.5',
        '  engine=<span class="ok">nautilus</span>  data=<span class="ok">polars</span>',
        '  <span class="dim">result:</span> sharpe=<span class="ok">1.87</span>  max_dd=<span class="ok">-6.42%</span>',
      ],
    },
    {
      q: 'Find docs that explain tool dispatch.',
      a: [
        '<span class="info">digisearch</span> → hybrid query (BM25 + dense, reranked)',
        '  <span class="dim">[0.913]</span> digigraph/orchestration/supervisor.py',
        '  <span class="dim">[0.881]</span> docs/ARCHITECTURE.md#tool-dispatch',
        '  <span class="dim">[0.842]</span> digigraph/orchestration/registry.py',
      ],
    },
  ];

  const bootLines = [
    '<span class="dim">[digithings]</span> booting core stack…',
    '<span class="dim">[digigraph]</span>   supervisor <span class="ok">ok</span>   :8000',
    '<span class="dim">[digiquant]</span>   atlas      <span class="ok">ok</span>   :8001',
    '<span class="dim">[digisearch]</span>  index      <span class="ok">ok</span>   :8002',
    '<span class="dim">[digichat]</span>    bff        <span class="ok">ok</span>   :3005',
    '<span class="dim">[litellm]</span>     proxy      <span class="ok">ok</span>   :4000',
    'ready.',
  ];

  async function heroLoop() {
    // initial: type `digithings init` → boot → blank → query loop
    cursor1.hidden = false;
    await typeInto(typedInit, 'digithings init', cursor1);
    cursor1.hidden = true;
    await sleep(prefersReduced ? 0 : 260);
    await printLines(heroBoot, bootLines, prefersReduced ? 0 : 90);
    await sleep(prefersReduced ? 0 : 600);

    let i = 0;
    while (true) {
      // show query prompt
      heroLine2.hidden = false;
      typedQuery.textContent = '';
      cursor2.hidden = false;
      await typeInto(typedQuery, queries[i].q, cursor2);
      cursor2.hidden = true;
      await sleep(prefersReduced ? 0 : 280);
      await printLines(heroAnswer, queries[i].a, prefersReduced ? 0 : 140);
      await sleep(prefersReduced ? 1500 : 3800);

      // "clear" and loop
      heroLine2.hidden = true;
      heroAnswer.hidden = true;
      heroAnswer.innerHTML = '';
      await sleep(prefersReduced ? 0 : 400);

      i = (i + 1) % queries.length;
      if (prefersReduced) break; // one pass only for reduced motion
    }
  }

  heroLoop().catch(() => {});

  /* ------------------------------------------------------ ecosystem */
  let ecoRan = false;
  async function runEcosystem() {
    if (ecoRan) return;
    ecoRan = true;
    const eco1 = document.getElementById('eco1');
    const eco2 = document.getElementById('eco2');
    const eco3 = document.getElementById('eco3');

    const seq1 = [
      '<span class="dim">[+]</span> Pulling digigraph:latest',
      '<span class="dim">[+]</span> Pulling digiquant:latest',
      '<span class="dim">[+]</span> Pulling digisearch:latest',
      '<span class="dim">[+]</span> Pulling digichat:latest',
      'digigraph-1   | Uvicorn running on http://0.0.0.0:8000',
      'digiquant-1   | Atlas ready (strategies=42)',
      'digisearch-1  | Index open, 12,480 chunks',
      'digichat-1    | Next.js ready on :3005',
      '<span class="ok">✓ stack up in 4.2s</span>',
    ];
    const seq2 = [
      '<span class="dim">→</span> handshake <span class="ok">ok</span>',
      '<span class="dim">→</span> discovering tools…',
      '  <span class="str">"digigraph.route"</span>     orchestrate a prompt',
      '  <span class="str">"digiquant.backtest"</span>  run a strategy',
      '  <span class="str">"digisearch.query"</span>    hybrid retrieval',
      '  <span class="str">"digichat.stream"</span>     scoped chat session',
      '<span class="ok">✓ 4 tools registered</span>',
    ];
    const seq3 = [
      'Collecting digigraph',
      '  Downloading digigraph-0.9.3-py3-none-any.whl (186 kB)',
      'Successfully installed <span class="ok">digigraph-0.9.3</span>',
      '',
      '<span class="kw">from</span> digigraph <span class="kw">import</span> Client',
      'client = Client(base_url=<span class="str">"http://localhost:8000"</span>)',
      'reply = client.run(<span class="str">"summarize today\'s market"</span>)',
      '<span class="dim"># → reply.text, reply.citations, reply.trace_id</span>',
    ];

    await Promise.resolve();
    await printLines(eco1, seq1, prefersReduced ? 0 : 140);
    await printLines(eco2, seq2, prefersReduced ? 0 : 160);
    await printLines(eco3, seq3, prefersReduced ? 0 : 150);
  }
})();
