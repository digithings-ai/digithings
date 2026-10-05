/**
 * The one place mermaid gets told what colour anything is.
 *
 * Extracted from `ChatMermaidBlock` so every mermaid surface in the kit — the
 * chat fence and the architecture diagram — resolves the same palette the same
 * way, and a token added for one is a token added for both.
 *
 * THE RULE: mermaid gets `theme: "base"` — the only built-in palette that lets
 * every `themeVariable` through — and every variable is filled from the
 * *computed* value of a design token read off the host element. Reading off the
 * host rather than `:root` means a livery scope (`.accent-digichat`,
 * `.accent-digiquant`) or a nested `[data-theme]` resolves exactly the colours
 * the surrounding section resolves.
 *
 * Tokens that do not resolve (tokens.css not loaded, non-browser) are omitted,
 * so mermaid falls back to its own value for that variable rather than being
 * handed an empty string it cannot parse.
 */

/**
 * mermaid themeVariable -> design token. Kept explicit (rather than letting
 * mermaid derive everything from `primaryColor`) because its derivation runs
 * khroma lighten/darken on whatever it is given, and the canon palette is not a
 * ramp — `--ink-mute` is the line colour in both themes, not a shade of the
 * node fill. Diagram kinds beyond flowchart borrow these too: the sequence,
 * state, class, ER and architecture renderers all read actor/label/note/
 * attribute/border vars.
 */
export const THEME_TOKENS: ReadonlyArray<readonly [string, string]> = [
  // canvas + type
  ["background", "--surface"],
  ["textColor", "--ink-soft"],
  ["titleColor", "--ink"],
  // nodes
  ["primaryColor", "--surface-2"],
  ["primaryTextColor", "--ink"],
  ["primaryBorderColor", "--accent"],
  ["secondaryColor", "--surface"],
  ["secondaryTextColor", "--ink"],
  ["secondaryBorderColor", "--hair-2"],
  ["tertiaryColor", "--surface"],
  ["tertiaryTextColor", "--ink-soft"],
  ["tertiaryBorderColor", "--hair-2"],
  ["mainBkg", "--surface-2"],
  ["nodeBorder", "--accent"],
  ["nodeTextColor", "--ink"],
  // edges + clusters
  ["lineColor", "--ink-mute"],
  ["edgeLabelBackground", "--surface"],
  ["clusterBkg", "--surface"],
  ["clusterBorder", "--hair-2"],
  // architecture (v11 architecture-beta)
  ["archEdgeColor", "--ink-mute"],
  ["archEdgeArrowColor", "--ink-mute"],
  ["archGroupBorderColor", "--hair-2"],
  // sequence
  ["actorBkg", "--surface-2"],
  ["actorBorder", "--accent"],
  ["actorTextColor", "--ink"],
  ["actorLineColor", "--ink-mute"],
  ["signalColor", "--ink-mute"],
  ["signalTextColor", "--ink-soft"],
  ["activationBkgColor", "--surface-2"],
  ["activationBorderColor", "--accent"],
  ["sequenceNumberColor", "--surface"],
  ["labelBoxBkgColor", "--surface-2"],
  ["labelBoxBorderColor", "--hair-2"],
  ["labelTextColor", "--ink"],
  ["loopTextColor", "--ink-soft"],
  ["noteBkgColor", "--surface"],
  ["noteBorderColor", "--hair-2"],
  ["noteTextColor", "--ink-soft"],
  ["altBackground", "--surface-2"],
  // class / ER / state
  ["classText", "--ink"],
  ["attributeBackgroundColorOdd", "--surface"],
  ["attributeBackgroundColorEven", "--surface-2"],
  // pie / quadrant chrome (categorical slice hues stay mermaid's — the canon
  // has no categorical ramp in the token layer)
  ["pieTitleTextColor", "--ink"],
  ["pieSectionTextColor", "--ink"],
  ["pieLegendTextColor", "--ink-soft"],
  ["pieStrokeColor", "--surface"],
  ["pieOuterStrokeColor", "--hair-2"],
  // failure chrome — the negative-semantics token, so a bad node reads red in
  // both themes without a literal
  ["errorBkgColor", "--surface"],
  ["errorTextColor", "--down"],
];

/**
 * Stroke widths are numbers, not colours, so they cannot come from a token —
 * they are pinned here to the kit's hairline weight so an architecture diagram
 * draws at the same weight as every other rule on the page.
 */
const THEME_LITERALS: ReadonlyArray<readonly [string, string]> = [
  ["archEdgeWidth", "1.4"],
  ["archGroupBorderWidth", "1"],
];

/** Resolve THEME_TOKENS against `host`'s computed style. */
export function tokenThemeVariables(host: Element): Record<string, string | boolean> {
  const cs = window.getComputedStyle(host);
  const vars: Record<string, string | boolean> = {};
  for (const [key, token] of THEME_TOKENS) {
    const value = cs.getPropertyValue(token).trim();
    if (value) vars[key] = value;
  }
  for (const [key, value] of THEME_LITERALS) vars[key] = value;
  const mono = cs.getPropertyValue("--font-mono").trim();
  if (mono) vars.fontFamily = mono;
  // mermaid's own lighten/darken direction for anything it still derives.
  vars.darkMode = document.documentElement.getAttribute("data-theme") !== "light";
  return vars;
}
