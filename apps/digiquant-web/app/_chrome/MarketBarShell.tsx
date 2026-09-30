/** Empty MarketBar shell (Phase 0a). Real feeds land in the hero/price-bar pass;
 *  until then it says so rather than showing any price. */
export function MarketBarShell() {
  return (
    <div className="relative z-10 border-b border-hair font-mono text-[0.68rem] text-ink-mute">
      <div className="mx-auto flex h-8 w-full max-w-[var(--frame-w)] items-center gap-3 px-[var(--page-pad)]">
        <span>[market]</span>
        <span className="text-ink-soft">connecting…</span>
        <span className="ms-auto hidden sm:inline">no feed connected in this build</span>
      </div>
    </div>
  );
}
