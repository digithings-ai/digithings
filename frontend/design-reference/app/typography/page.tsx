import "./typography.css";
import { CopyGrammarReference } from "@/components/copy-grammar-reference";
import { WordRevealReference } from "@/components/word-reveal-reference";
import { WordRevealMuted } from "@/components/word-reveal-muted";
import { WordRevealOutline } from "@/components/word-reveal-outline";

export default function TypographyPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// typography"}</p>
        <h1>
          Scroll-linked <em>word reveals.</em>
        </h1>
        <p>
          The two-voice type system (Fraunces for claims, Geist Mono for data) plus the reveal
          grammar: how long copy earns attention on scroll. Three variants — pinned blur, muted
          base, outline fill — all pinning the line until every word is fully visible.
        </p>
      </header>

      <WordRevealReference />
      <WordRevealMuted />
      <WordRevealOutline />
      <CopyGrammarReference />
    </main>
  );
}
