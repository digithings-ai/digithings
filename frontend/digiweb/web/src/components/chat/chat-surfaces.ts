/**
 * Surface class strings for the first-party digichat Thread — the digiweb analog
 * of assistant-ui `surfaces.tsx`. Paper / field / live / mono / code sit on
 * `[data-theme]` + `--term-*` + rose livery (see styles/chat-aui.css). No pills.
 */

export const DIGICHAT_GLYPHS = {
  user: ">",
  assistant: "▸",
  system: "·",
} as const;

export const digichatSurfaces = {
  thread:
    "digichat-thread flex h-full min-h-0 flex-col bg-term-bg font-mono text-term-ink",
  viewport:
    "digichat-thread__viewport flex min-h-0 flex-1 flex-col gap-[0.7rem] overflow-y-auto overscroll-contain px-[1.15rem] pt-[1rem] pb-[1.2rem]",
  footer: "digichat-thread__footer sticky bottom-0 flex flex-col gap-[0.45rem] bg-term-bg pt-[0.4rem] pb-[0.2rem]",
  welcome: "flex flex-col gap-[0.7rem] py-[1.2rem]",
  welcomeKicker: "m-0 font-mono text-[0.62rem] tracking-[0.06em] text-term-mute",
  welcomeTitle: "m-0 max-w-[36rem] font-mono text-[1.05rem] font-normal leading-[1.4] tracking-[-0.02em] text-term-ink",
  suggestions: "flex flex-wrap gap-[0.45rem]",
  chip: "digichat-chip cursor-pointer rounded-none border border-hair bg-transparent px-[0.7rem] py-[0.35rem] text-left font-mono text-[0.72rem] text-ink-soft",
  turn: "digichat-turn flex flex-col items-stretch gap-[0.2rem]",
  composer:
    "digichat-composer flex flex-col gap-[0.45rem] rounded-none border border-hair bg-surface px-[0.85rem] pt-[0.75rem] pb-[0.6rem]",
  composerRow: "flex items-start gap-[0.55rem]",
  composerGlyph: "shrink-0 select-none font-mono text-[0.9rem] leading-[1.5] text-accent",
  composerInput:
    "min-h-[1.5rem] w-full resize-none border-0 bg-transparent font-mono text-[0.9rem] leading-[1.5] text-ink outline-none",
  composerTray: "flex items-center justify-between gap-[0.75rem]",
  action:
    "digichat-action inline-flex cursor-pointer items-center rounded-none border-0 bg-transparent p-0 font-mono text-[0.66rem] tracking-[0.02em] text-ink-mute",
  actionRow:
    "digichat-action-row mt-[0.25rem] ml-[1.8rem] flex flex-wrap items-center gap-[0.75rem]",
  send: "inline-flex h-8 cursor-pointer items-center justify-center rounded-none border-0 bg-ink px-[0.85rem] font-mono text-[0.72rem] text-bg disabled:opacity-40",
  stop: "inline-flex h-8 cursor-pointer items-center justify-center rounded-none border border-hair bg-transparent px-[0.85rem] font-mono text-[0.72rem] text-ink",
  scrollBtn:
    "digichat-scroll-btn mx-auto cursor-pointer rounded-none border border-hair bg-surface px-[0.6rem] py-[0.2rem] font-mono text-[0.66rem] text-ink-mute",
  attach: "digichat-attach inline-flex items-center gap-[0.35rem] border border-hair px-[0.45rem] py-[0.15rem] font-mono text-[0.66rem] text-ink-soft",
  error: "ml-[1.8rem] mt-[0.35rem] border border-danger/40 px-[0.7rem] py-[0.4rem] font-mono text-[0.78rem] text-danger",
  list: "digichat-thread-list flex w-56 shrink-0 flex-col border-r border-term-hair bg-term-bg font-mono",
  listItem:
    "digichat-thread-list__item w-full truncate rounded-none border-0 bg-transparent px-[0.7rem] py-[0.4rem] text-left font-mono text-[0.78rem] text-term-ink data-[active]:bg-term-fill",
  pane: "flex h-full min-h-0 flex-col rounded-none border border-term-hair bg-term-bg",
} as const;
