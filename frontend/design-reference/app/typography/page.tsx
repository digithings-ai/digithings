import "./typography.css";
import { WordRevealReference } from "@/components/word-reveal-reference";

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
          grammar: how long copy earns attention on scroll.
        </p>
      </header>

      <WordRevealReference />
    </main>
  );
}
