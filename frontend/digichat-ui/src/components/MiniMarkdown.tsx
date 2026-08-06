import { ChatMarkdown } from "@digithings/web";

/**
 * Markdown renderer for streamed model output — a thin delegate to the shared
 * `<ChatMarkdown>` (`@digithings/web`), which owns the `.chat-md` grammar,
 * GFM tables, fenced code with copy, mermaid diagrams and LaTeX.
 *
 * This used to be an app-local react-markdown pipeline with its own `.dc-md-*`
 * node map and a local `MermaidBlock` (#1418 gap 3). It rendered the same answer
 * differently from digithings.ai — a 0.8rem mono scale against the shared
 * 0.88rem body — and the two renderers drifted independently. The embed now
 * adopts the shared scale, so a docs answer reads identically on both surfaces.
 *
 * The local `MermaidBlock` is retired rather than kept: the shared diagram path
 * is strictly richer, not thinner — `securityLevel: "strict"`, a malformed graph
 * contained instead of injecting mermaid's error-bomb SVG, and the diagram source
 * rendered verbatim as the no-JS / parse-failure fallback.
 *
 * Styling arrives via `@digithings/web/styles/chat-core.css`, already imported by
 * digichat's `globals.css`. Nothing here carries a `.dc-md-*` class any more, so
 * the old rules in `session.css` were removed with it.
 */
export function MiniMarkdown({ text }: { text: string }) {
  return <ChatMarkdown source={text} />;
}
