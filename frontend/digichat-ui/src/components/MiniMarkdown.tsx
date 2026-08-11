import { ChatMarkdown } from "@digithings/web";

/**
 * Markdown renderer for streamed model output — a thin delegate to the shared
 * `<ChatMarkdown>` (`@digithings/web`), which owns the `.chat-md` grammar,
 * GFM tables, fenced code with copy, mermaid diagrams and LaTeX.
 *
 * This used to be an app-local react-markdown pipeline with its own `.dc-md-*`
 * node map and a local `MermaidBlock` (#1418 gap 3).
 *
 * IT IS SHARED BY BOTH SURFACES TODAY. An earlier version of this docblock claimed
 * the old pipeline "rendered the same answer differently from digithings.ai" and
 * that "the two renderers drifted independently". Neither held: digithings-web did
 * once carry a forked `lib/miniMarkdown.tsx` and pass it as
 * `renderAssistantContent`, but the two files were byte-identical apart from a
 * docblock, so the output never differed and nothing drifted. #1450 (`ae4d4a33`,
 * 2026-07-10) deleted the fork, and since then neither app overrides the prop.
 *
 * So at #1941 this component was the only renderer for both surfaces, and replacing
 * its pipeline re-typeset the public /chat page too — 0.8rem body with 0.85rem mono
 * headings became the shared 0.88rem body with 1.15rem serif-display headings. That
 * was reviewed after the fact and the shared canon was kept deliberately.
 *
 * So: any edit here lands on digichat /embed AND digithings.ai/chat. There is no
 * embed-only change to make in this file.
 *
 * The local `MermaidBlock` is retired rather than kept: the shared diagram path
 * is strictly richer, not thinner — `securityLevel: "strict"`, a malformed graph
 * contained instead of injecting mermaid's error-bomb SVG, and the diagram source
 * rendered verbatim as the no-JS / parse-failure fallback.
 *
 * Styling arrives via `@digithings/web/styles/chat-core.css` plus
 * `chat-math.css` for LaTeX, both imported by digichat's and digithings-web's
 * `globals.css`. Nothing here carries a `.dc-md-*` class any more, so the old
 * rules in `session.css` were removed with it.
 */
export function MiniMarkdown({ text }: { text: string }) {
  return <ChatMarkdown source={text} />;
}
