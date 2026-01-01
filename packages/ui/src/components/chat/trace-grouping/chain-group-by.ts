import { groupPartByType } from "@assistant-ui/react";

/**
 * The chain grouping every first-party trace uses (the digichat skin's
 * gallery thread, the base skins and the stock thread).
 *
 * Reasoning and tool calls nest under one `group-chainOfThought`, and inside
 * it adjacent reasoning parts coalesce into `group-reasoning` and adjacent
 * tool calls into `group-tool`.
 *
 * A source or a status part between two work runs must not split the chain:
 * only text ends a work run, so two runs with nothing but a source between
 * them are one chain, not two. The library's helper covers the part types it
 * knows; the status parts (`data-*`) are matched here, and the memo
 * fingerprint is kept so the tree is not rebuilt on every render.
 */
export const chainGroupBy = (() => {
  const base = groupPartByType({
    reasoning: ["group-chainOfThought", "group-reasoning"],
    "tool-call": ["group-chainOfThought", "group-tool"],
    "standalone-tool-call": [],
    source: ["group-chainOfThought", "group-tool"],
  });
  const fn = (part: { type: string; name?: string }, context?: unknown) => {
    const dataName =
      part.type === "data"
        ? part.name
        : part.type.startsWith("data-")
          ? part.type.slice("data-".length)
          : undefined;
    // A data-notice (a rate-limit wait, and any other status notice) stays
    // outside the chain. The chain folds once the answer arrives, which would
    // hide the notice inside the collapsed work block.
    if (dataName === "notice") return base(part as never, context as never);
    if (part.type === "data" || part.type.startsWith("data-")) {
      return ["group-chainOfThought", "group-tool"] as const;
    }
    return base(part as never, context as never);
  };
  (fn as unknown as Record<symbol, string>)[
    Symbol.for("@assistant-ui/groupBy.memoKey")
  ] = "digichat:chain-v3";
  return fn;
})();
