# score:allow pandas
"""Tearsheet HTML page assembly (layout, CSS, tabs)."""

from __future__ import annotations

from digiquant.models import BacktestResult


def _build_page(
    result: BacktestResult,
    strategy_display: str,
    symbols_str: str,
    params_str: str,
    win_rate: float | None,
    profit_factor: float | None,
    sortino: float | None,
    calmar: float | None,
    price_gen: str,
    price_tab: str,
    equity_gen: str,
    equity_tab: str,
    dd_gen: str,
    dd_tab: str,
    monthly_gen: str,
    dist_gen: str,
    dist_tab: str,
    rolling_gen: str,
    rolling_tab: str,
    yearly_gen: str,
    rolling_equity_html: str,
    realized_pnl_html: str,
    trade_pnl_dist_html: str,
    trade_pnl_dist_trades_html: str,
    rolling_dd_html: str,
    monthly_yearly_html: str,
    per_trade_pnl_html: str,
    win_rate_donut_html: str,
    rolling_calmar_html: str,
    cum_trade_pnl_html: str,
    underwater_html: str,
    full_stats_html: str = "",
    risk_metrics_html: str = "",
    categorized_stats_html: str = "",
    logo_data_url: str = "",
) -> str:
    md_val = result.max_drawdown_pct
    md = f"{md_val:.1f}%" if md_val is not None else "—"
    sharpe_str = f"{result.sharpe_ratio:.2f}" if result.sharpe_ratio is not None else "—"
    win_rate_str = f"{win_rate * 100:.1f}%" if win_rate is not None else "—"
    pf_str = f"{profit_factor:.2f}" if profit_factor is not None else "—"
    sortino_str = f"{sortino:.2f}" if sortino is not None else "—"
    calmar_str = f"{calmar:.2f}" if calmar is not None else "—"
    ret_cls = "positive" if result.total_return_pct >= 0 else "negative"
    md_cls = "negative" if (md_val is not None and md_val < 0) else ""
    rolling_window_label = "60-day"

    def kpi(label: str, value: str, cls: str = "", sub: str = "") -> str:
        sub_html = f'<span class="kpi-sub">{sub}</span>' if sub else ""
        return f'<div class="kpi"><span class="kpi-label">{label}</span><span class="kpi-value {cls}">{value}</span>{sub_html}</div>'

    kpis = (
        kpi("TOTAL RETURN", f"{result.total_return_pct:+.2f}%", ret_cls)
        + kpi(
            "SHARPE",
            sharpe_str,
            "positive" if result.sharpe_ratio and result.sharpe_ratio > 1 else "",
        )
        + kpi("SORTINO", sortino_str, "positive" if sortino and sortino > 1 else "")
        + kpi("MAX DRAWDOWN", md, md_cls)
        + kpi(
            "WIN RATE",
            win_rate_str,
            "positive"
            if win_rate and win_rate > 0.5
            else "negative"
            if win_rate and win_rate < 0.4
            else "",
        )
        + kpi(
            "PROFIT FACTOR",
            pf_str,
            "positive"
            if profit_factor and profit_factor > 1.5
            else "negative"
            if profit_factor and profit_factor < 1
            else "",
        )
        + kpi("TOTAL TRADES", str(result.num_trades))
        + kpi("CALMAR", calmar_str, "positive" if calmar and calmar > 1 else "")
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Backtest Report — {strategy_display}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    /* ── Reset & Root ────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #080d14;
      --bg2: #0c1420;
      --card: #0f1c2e;
      --card2: #132035;
      --border: rgba(56,189,248,0.12);
      --border2: rgba(255,255,255,0.06);
      --text: #e2e8f0;
      --text-muted: #64748b;
      --text-dim: #334155;
      --accent: #38bdf8;
      --accent2: #0ea5e9;
      --positive: #34d399;
      --negative: #f87171;
      --warn: #fbbf24;
      --purple: #a78bfa;
      --font-mono: 'IBM Plex Mono', 'Courier New', monospace;
      --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
    }}
    [data-theme="light"] {{
      --bg: #f0f4f8; --bg2: #e8edf3; --card: #ffffff; --card2: #f8fafc;
      --border: rgba(14,165,233,0.15); --border2: rgba(0,0,0,0.07);
      --text: #0f172a; --text-muted: #475569; --text-dim: #94a3b8;
      --accent: #0ea5e9; --accent2: #0284c7;
      --positive: #059669; --negative: #dc2626; --warn: #d97706;
    }}
    body {{
      font-family: var(--font-sans); background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.5;
      background-image: radial-gradient(ellipse at 20% 0%, rgba(56,189,248,0.04) 0%, transparent 50%),
                        radial-gradient(ellipse at 80% 100%, rgba(167,139,250,0.03) 0%, transparent 50%);
    }}
    /* ── Layout ──────────────────────────────────────────── */
    .page {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem 2rem 3rem; }}
    /* ── Header ──────────────────────────────────────────── */
    .header {{
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 1.5rem; padding-bottom: 1rem;
      border-bottom: 1px solid var(--border2);
    }}
    .header-left {{ display: flex; align-items: center; gap: 1rem; }}
    .logo {{ height: 36px; width: auto; object-fit: contain; }}
    .header-title {{
      display: flex; flex-direction: column; gap: 0.1rem;
    }}
    .header-title h1 {{
      font-family: var(--font-mono); font-size: 1.1rem; font-weight: 600;
      color: var(--text); letter-spacing: 0.05em;
    }}
    .header-title .subtitle {{
      font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted);
      letter-spacing: 0.1em;
    }}
    .header-right {{ display: flex; align-items: center; gap: 1rem; }}
    .date-badge {{
      font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted);
      background: var(--card); border: 1px solid var(--border2); border-radius: 6px;
      padding: 0.35rem 0.75rem; letter-spacing: 0.05em;
    }}
    .theme-btn {{
      padding: 0.35rem 0.75rem; background: var(--card); border: 1px solid var(--border2);
      border-radius: 6px; cursor: pointer; font-family: var(--font-sans); font-size: 0.75rem;
      color: var(--text-muted); transition: all 0.15s;
    }}
    .theme-btn:hover {{ border-color: var(--accent); color: var(--text); }}
    /* ── Strategy info bar ───────────────────────────────── */
    .info-bar {{
      display: flex; gap: 2rem; align-items: center; flex-wrap: wrap;
      padding: 0.75rem 1.25rem; background: var(--card); border: 1px solid var(--border2);
      border-radius: 10px; margin-bottom: 1.25rem; font-family: var(--font-mono); font-size: 0.75rem;
    }}
    .info-item {{ display: flex; gap: 0.5rem; align-items: center; }}
    .info-label {{ color: var(--text-muted); }}
    .info-value {{ color: var(--accent); font-weight: 500; }}
    /* ── KPI Strip ───────────────────────────────────────── */
    .kpi-strip {{
      display: grid; grid-template-columns: repeat(8, 1fr); gap: 0.6rem;
      margin-bottom: 1.25rem;
    }}
    @media (max-width: 1100px) {{ .kpi-strip {{ grid-template-columns: repeat(4, 1fr); }} }}
    @media (max-width: 600px) {{ .kpi-strip {{ grid-template-columns: repeat(2, 1fr); }} }}
    .kpi {{
      background: var(--card); border: 1px solid var(--border2); border-radius: 10px;
      padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.3rem;
      transition: border-color 0.15s;
      position: relative; overflow: hidden;
    }}
    .kpi::before {{
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
      background: var(--accent); opacity: 0.3; transition: opacity 0.15s;
    }}
    .kpi:hover {{ border-color: var(--border); }}
    .kpi:hover::before {{ opacity: 0.8; }}
    .kpi-label {{ font-family: var(--font-mono); font-size: 0.6rem; color: var(--text-muted); letter-spacing: 0.12em; text-transform: uppercase; }}
    .kpi-value {{ font-family: var(--font-mono); font-size: 1.25rem; font-weight: 600; color: var(--text); }}
    .kpi-value.positive {{ color: var(--positive); }}
    .kpi-value.negative {{ color: var(--negative); }}
    .kpi-sub {{ font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-muted); }}
    /* ── Stats grid (expanded metrics) ──────────────────── */
    .stats-toggle-wrap {{ margin-bottom: 1.25rem; }}
    .stats-toggle-btn {{
      display: flex; align-items: center; gap: 0.5rem; padding: 0.45rem 1rem;
      background: var(--card); border: 1px solid var(--border2); border-radius: 8px;
      cursor: pointer; font-family: var(--font-sans); font-size: 0.8rem; color: var(--text-muted);
      transition: all 0.15s;
    }}
    .stats-toggle-btn:hover {{ border-color: var(--accent); color: var(--text); }}
    .stats-toggle-btn .arrow {{ font-size: 0.6rem; transition: transform 0.2s; }}
    .stats-toggle-btn.open .arrow {{ transform: rotate(180deg); }}
    .stats-panel {{
      display: none; padding: 1.25rem; background: var(--card); border: 1px solid var(--border2);
      border-radius: 10px; margin-top: 0.5rem;
    }}
    .stats-panel.open {{ display: block; }}
    .stats-grid {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.25rem;
    }}
    @media (max-width: 900px) {{ .stats-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .stats-section {{ }}
    .stats-section-title {{
      font-family: var(--font-mono); font-size: 0.65rem; text-transform: uppercase;
      letter-spacing: 0.1em; color: var(--accent); margin-bottom: 0.6rem;
      padding-bottom: 0.4rem; border-bottom: 1px solid var(--border2);
    }}
    .stats-mini-table {{ width: 100%; border-collapse: collapse; }}
    .stats-mini-table tr:not(:last-child) td {{ border-bottom: 1px solid var(--border2); }}
    .stats-mini-table .sk {{
      padding: 0.3rem 0; font-family: var(--font-sans); font-size: 0.75rem; color: var(--text-muted); width: 60%;
    }}
    .stats-mini-table .sv {{
      padding: 0.3rem 0; font-family: var(--font-mono); font-size: 0.75rem; color: var(--text); text-align: right;
    }}
    .stats-mini-table .sv.pos {{ color: var(--positive); }}
    .stats-mini-table .sv.neg {{ color: var(--negative); }}
    /* ── Tabs ────────────────────────────────────────────── */
    .tabs {{
      display: flex; gap: 0.25rem; margin-bottom: 1rem; flex-wrap: wrap;
      border-bottom: 1px solid var(--border2); padding-bottom: 0.75rem;
    }}
    .tab {{
      padding: 0.4rem 1rem; border: 1px solid transparent; border-radius: 6px;
      cursor: pointer; font-family: var(--font-sans); font-size: 0.8rem; color: var(--text-muted);
      background: transparent; transition: all 0.15s; font-weight: 500;
    }}
    .tab:hover {{ color: var(--text); border-color: var(--border2); }}
    .tab.active {{ background: var(--accent); color: #0c1420; border-color: var(--accent); font-weight: 600; }}
    /* ── Tab content & chart wraps ───────────────────────── */
    .tab-content {{ display: none; }}
    .chart-wrap {{
      background: var(--card); border: 1px solid var(--border2); border-radius: 10px;
      padding: 1rem 1rem 0.75rem; position: relative; overflow: hidden;
    }}
    .chart-wrap-title {{
      font-family: var(--font-mono); font-size: 0.7rem; text-transform: uppercase;
      letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: 0.5rem;
    }}
    /* Overview tab: 2-col grid */
    #overview.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #overview.active .span-2 {{ grid-column: 1 / -1; }}
    /* Equity & Returns tab */
    #equity-returns.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #equity-returns.active .span-2 {{ grid-column: 1 / -1; }}
    /* Risk tab */
    #risk.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #risk.active .span-2 {{ grid-column: 1 / -1; }}
    /* Trades tab */
    #trades.active {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
    }}
    #trades.active .span-2 {{ grid-column: 1 / -1; }}
    /* Price tab */
    #price.active {{ display: block; }}
    /* Plotly heights */
    .h-sm  .plotly-graph-div {{ min-height: 220px !important; height: 220px !important; }}
    .h-md  .plotly-graph-div {{ min-height: 280px !important; height: 280px !important; }}
    .h-lg  .plotly-graph-div {{ min-height: 300px !important; height: 300px !important; }}
    .h-xl  .plotly-graph-div {{ min-height: 480px !important; height: 480px !important; }}
    .h-monthly .plotly-graph-div {{ min-height: 200px !important; height: auto !important; }}
    /* ── Risk metrics table ──────────────────────────────── */
    .metrics-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
    .metrics-table th, .metrics-table td {{ padding: 0.45rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border2); }}
    .metrics-table th {{ font-family: var(--font-mono); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); }}
    .metrics-table td:first-child {{ color: var(--text-muted); font-family: var(--font-sans); }}
    .metrics-table td:last-child {{ font-family: var(--font-mono); color: var(--text); text-align: right; }}
    /* ── No-data placeholder ─────────────────────────────── */
    .no-data {{ color: var(--text-muted); padding: 3rem 2rem; text-align: center; font-family: var(--font-mono); font-size: 0.8rem; letter-spacing: 0.05em; }}
    .chart-unavailable {{ border: 1px dashed rgba(148,163,184,0.35); border-radius: 8px; padding: 2rem 1.5rem; text-align: center; background: rgba(15,23,42,0.4); }}
    .chart-unavailable-title {{ color: var(--text-muted); font-family: var(--font-mono); font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 0.5rem; }}
    .chart-unavailable-detail {{ color: #64748b; font-size: 0.8rem; margin: 0; }}
    /* ── Footer ──────────────────────────────────────────── */
    .footer {{
      margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border2);
      font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-dim);
      display: flex; justify-content: space-between; align-items: center;
    }}
    /* ── Print ───────────────────────────────────────────── */
    @media print {{
      body {{ background: white; color: black; }}
      .theme-btn, .stats-toggle-btn, .tabs {{ display: none; }}
      .tab-content {{ display: block !important; page-break-before: always; }}
    }}
  </style>
</head>
<body>
<div class="page">

  <!-- ── Header ── -->
  <div class="header">
    <div class="header-left">
      {f'<img src="{logo_data_url}" alt="Digi" class="logo" />' if logo_data_url else ""}
      <div class="header-title">
        <h1>BACKTEST REPORT</h1>
        <span class="subtitle">DIGIQUANT · NAUTILUSTRADER</span>
      </div>
    </div>
    <div class="header-right">
      <span class="date-badge">{result.start_time[:10]} → {result.end_time[:10]}</span>
      <button class="theme-btn" id="themeToggle">☀ Light</button>
    </div>
  </div>

  <!-- ── Strategy info bar ── -->
  <div class="info-bar">
    <div class="info-item"><span class="info-label">STRATEGY</span><span class="info-value">{strategy_display}</span></div>
    <div class="info-item"><span class="info-label">INSTRUMENTS</span><span class="info-value">{symbols_str}</span></div>
    <div class="info-item"><span class="info-label">PARAMS</span><span class="info-value">{params_str}</span></div>
    <div class="info-item"><span class="info-label">TOTAL P&L</span><span class="info-value" style="color:{"var(--positive)" if result.total_pnl >= 0 else "var(--negative)"}">${result.total_pnl:,.2f}</span></div>
  </div>

  <!-- ── KPI Strip ── -->
  <div class="kpi-strip">{kpis}</div>

  <!-- ── Expanded metrics panel ── -->
  <div class="stats-toggle-wrap">
    <button class="stats-toggle-btn" id="statsToggle">
      <span>Detailed metrics</span><span class="arrow">▼</span>
    </button>
    <div class="stats-panel" id="statsPanel">{categorized_stats_html}</div>
  </div>

  <!-- ── Tabs ── -->
  <div class="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="equity-returns">Equity &amp; Returns</button>
    <button class="tab" data-tab="risk">Risk</button>
    <button class="tab" data-tab="trades">Trades</button>
    <button class="tab" data-tab="price">Price</button>
  </div>

  <!-- ── Overview tab ── -->
  <div class="tab-content" id="overview">
    <div class="chart-wrap span-2 h-xl"><div class="chart-wrap-title">Price + Bollinger Bands + Entries &amp; Exits</div>{price_gen}</div>
    <div class="chart-wrap h-lg"><div class="chart-wrap-title">Equity Curve</div>{equity_gen}</div>
    <div class="chart-wrap h-sm"><div class="chart-wrap-title">Drawdown</div>{dd_gen}</div>
    <div class="chart-wrap span-2 h-monthly"><div class="chart-wrap-title">Monthly &amp; Yearly Returns</div>{monthly_yearly_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Returns Distribution</div>{dist_gen}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Sharpe Ratio</div>{rolling_gen}</div>
  </div>

  <!-- ── Equity & Returns tab ── -->
  <div class="tab-content" id="equity-returns">
    <div class="chart-wrap span-2 h-lg"><div class="chart-wrap-title">Rolling Equity (Daily)</div>{rolling_equity_html}</div>
    <div class="chart-wrap span-2 h-monthly"><div class="chart-wrap-title">Monthly &amp; Yearly Returns Heatmap</div>{monthly_yearly_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Returns Distribution</div>{dist_tab}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Sharpe ({rolling_window_label})</div>{rolling_tab}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Calmar Ratio</div>{rolling_calmar_html}</div>
    <div class="chart-wrap span-2 h-lg"><div class="chart-wrap-title">Cumulative Realized P&amp;L</div>{realized_pnl_html}</div>
  </div>

  <!-- ── Risk tab ── -->
  <div class="tab-content" id="risk">
    <div class="chart-wrap h-sm"><div class="chart-wrap-title">Drawdown</div>{dd_tab}</div>
    <div class="chart-wrap h-sm"><div class="chart-wrap-title">Underwater Equity</div>{underwater_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Rolling Max Drawdown (60-day)</div>{rolling_dd_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Trade P&amp;L Distribution</div>{trade_pnl_dist_html}</div>
    <div class="chart-wrap span-2"><div class="chart-wrap-title">Risk Metrics</div>{risk_metrics_html}</div>
  </div>

  <!-- ── Trades tab ── -->
  <div class="tab-content" id="trades">
    <div class="chart-wrap span-2 h-lg"><div class="chart-wrap-title">Per-Trade P&amp;L</div>{per_trade_pnl_html}</div>
    <div class="chart-wrap h-lg"><div class="chart-wrap-title">Cumulative P&amp;L by Trade #</div>{cum_trade_pnl_html}</div>
    <div class="chart-wrap h-md"><div class="chart-wrap-title">Win / Loss Split</div>{win_rate_donut_html}</div>
    <div class="chart-wrap span-2 h-md"><div class="chart-wrap-title">Trade P&amp;L Distribution (Winners vs Losers)</div>{trade_pnl_dist_trades_html}</div>
  </div>

  <!-- ── Price tab ── -->
  <div class="tab-content" id="price">
    <div class="chart-wrap h-xl"><div class="chart-wrap-title">Price + Bollinger Bands + Entries &amp; Exits</div>{price_tab}</div>
  </div>

  <div class="footer">
    <span>digiquant Backtest Report — Generated from NautilusTrader</span>
    <span id="gen-time"></span>
  </div>
</div>

<script>
(function() {{
  // ── Theme ──────────────────────────────────────────────────────────
  const STORAGE_KEY = 'dq-theme';
  const DARK_LAYOUT = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(255,255,255,0.03)',
    font: {{ color: '#94a3b8', family: "'IBM Plex Mono','Courier New',monospace", size: 11 }},
    xaxis: {{ gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.1)', tickfont: {{ color: '#64748b', size: 10 }} }},
    yaxis: {{ gridcolor: 'rgba(255,255,255,0.05)', linecolor: 'rgba(255,255,255,0.1)', tickfont: {{ color: '#64748b', size: 10 }} }},
  }};
  const LIGHT_LAYOUT = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0.02)',
    font: {{ color: '#475569', family: "'IBM Plex Mono','Courier New',monospace", size: 11 }},
    xaxis: {{ gridcolor: 'rgba(0,0,0,0.05)', linecolor: 'rgba(0,0,0,0.1)', tickfont: {{ color: '#94a3b8', size: 10 }} }},
    yaxis: {{ gridcolor: 'rgba(0,0,0,0.05)', linecolor: 'rgba(0,0,0,0.1)', tickfont: {{ color: '#94a3b8', size: 10 }} }},
  }};

  function isDark() {{ return document.documentElement.getAttribute('data-theme') !== 'light'; }}

  function applyTheme(dark) {{
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = dark ? '☀ Light' : '☾ Dark';
    try {{ localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light'); }} catch(e) {{}}
    if (typeof Plotly === 'undefined') return;
    const layout = dark ? DARK_LAYOUT : LIGHT_LAYOUT;
    document.querySelectorAll('.plotly-graph-div').forEach(div => {{
      if (!div.id) return;
      try {{ Plotly.relayout(div.id, layout); }} catch(e) {{}}
    }});
  }}

  const stored = (function() {{ try {{ return localStorage.getItem(STORAGE_KEY); }} catch(e) {{ return null; }} }})();
  const darkDefault = stored ? stored === 'dark' : true;
  document.documentElement.setAttribute('data-theme', darkDefault ? 'dark' : 'light');
  document.getElementById('themeToggle').textContent = darkDefault ? '☀ Light' : '☾ Dark';
  setTimeout(() => applyTheme(darkDefault), 200);
  document.getElementById('themeToggle').addEventListener('click', () => applyTheme(!isDark()));

  // ── Tabs ───────────────────────────────────────────────────────────
  document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      const el = document.getElementById(tab.dataset.tab);
      if (el) {{
        el.classList.add('active');
        if (typeof Plotly !== 'undefined') {{
          setTimeout(() => el.querySelectorAll('.plotly-graph-div').forEach(d => Plotly.Plots.resize(d)), 60);
        }}
      }}
    }});
  }});
  // Activate first tab
  const firstTab = document.querySelector('.tab-content[id="overview"]');
  if (firstTab) firstTab.classList.add('active');

  // ── Stats toggle ───────────────────────────────────────────────────
  const toggleBtn = document.getElementById('statsToggle');
  const statsPanel = document.getElementById('statsPanel');
  if (toggleBtn && statsPanel) {{
    toggleBtn.addEventListener('click', () => {{
      toggleBtn.classList.toggle('open');
      statsPanel.classList.toggle('open');
    }});
  }}

  // ── Generation timestamp ───────────────────────────────────────────
  const gt = document.getElementById('gen-time');
  if (gt) gt.textContent = 'Generated ' + new Date().toLocaleString();
}})();
</script>
</body>
</html>"""
