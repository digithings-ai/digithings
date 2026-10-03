/** Dev gallery pages: block ids per group (plain module so server and client code can both read it). */
export const GROUP_PAGES: Record<string, string[]> = {
  pipeline: ['pl-run-health', 'pl-canvas', 'pl-node-document', 'pl-narrative', 'pl-call-trace', 'pl-artifacts'],
  strategies: ['st-kpis', 'st-catalog', 'st-deployments', 'st-targets', 'st-overview', 'st-parameters', 'st-track-record', 'st-runs', 'st-deploy-flow', 'st-deploy-draft'],
  markets: ['mk-ticker-strip', 'mk-quote-board', 'mk-fx-crosses', 'mk-price-pane', 'mk-volume-pane', 'mk-rsi-pane', 'mk-ohlc-readout', 'mk-news-tape', 'mk-chart-series'],
  fx: ['fx-summary', 'fx-pairs', 'fx-pair-path', 'fx-ideas', 'fx-idea-detail', 'fx-levels', 'fx-flags', 'fx-paper-exposure', 'fx-directives', 'fx-sessions'],
  rates: ['rt-summary', 'rt-watchlist', 'rt-curve', 'rt-theses'],
  chat: ['ch-sessions', 'ch-thread', 'ch-transcript', 'ch-composer'],
  settings: ['se-prefs', 'se-desk', 'se-fx-feed', 'se-brokers', 'se-integrations', 'se-keys', 'sh-desks', 'sh-features', 'sh-pipeline-chip', 'sh-footer', 'sh-spine'],
};
