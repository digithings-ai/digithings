/** Tab flag for the digiquant pixel mark. Set before paint on a later load. */
export const HERO_PLAYED_KEY = "dq:hero-played";

/** Strict-mode remounts land inside this window. A navigation does not. */
export const HERO_ADOPT_MS = 80;

export const HERO_PLAYED_SCRIPT = [
  "(function(){try{",
  `var k=${JSON.stringify(HERO_PLAYED_KEY)};`,
  'if(sessionStorage.getItem(k)==="1")',
  'document.documentElement.setAttribute("data-dq-hero","played");',
  'else sessionStorage.setItem(k,"1");',
  "}catch(e){}})();",
].join("");

export type HeroGateView = { started: number; connected: boolean };

/** Whether this mount should run the rise. `claim` records the play. */
export function nextHeroLive(input: {
  played: boolean;
  armed: boolean;
  idle: boolean;
  now: number;
  gate: HeroGateView | null;
}): { live: boolean; claim: boolean } {
  if (!input.armed || input.idle) return { live: false, claim: false };
  if (input.played) {
    const young =
      !!input.gate && input.now - input.gate.started < HERO_ADOPT_MS && !input.gate.connected;
    return { live: young, claim: false };
  }
  return { live: true, claim: true };
}
