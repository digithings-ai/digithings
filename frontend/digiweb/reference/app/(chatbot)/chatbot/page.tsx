import "./chatbot.css";
import { ChatbotThreadSpecimen } from "@/components/chatbot/chatbot-thread-specimen";
import { ChatbotChromeSpecimen } from "@/components/chatbot/chatbot-chrome-specimen";
import { CubeMatrixLegend } from "@/components/chatbot/cube-matrix-legend";

export default function ChatbotPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// chatbot"}</p>
        <h1>
          The official Thread, <em>themed.</em>
        </h1>
        <p>
          This page is the default assistant-ui <code>Thread</code> from the
          registry — welcome, messages, markdown, reasoning, tools, composer —
          with no custom message tree. Shell: radius 0, monochrome ink.
          Welcome: official <code>components.Welcome</code> slot, in the
          footer immediately above the composer. Copy is
          deploy-config shaped (title + body). Optional <code>&gt;</code>{" "}
          starters from config — not chips, not a top-of-thread empty state.
          Two composers: expanded (toolbar under the input) and
          compact (attach · field · send on one row). Send stays quiet until
          there is text, then fills. Enter and the send key both submit.
          Transcript: both roles left, <code>&gt;</code> user / <code>▸</code>{" "}
          assistant, no bubbles. Waiting: 5×5 cube matrix, cubes snap on and
          off. Reasoning: square caret, hairline rail, no pill. Theme toggle
          still flips light/dark.
        </p>
      </header>
      <section className="section-block" id="matrix">
        <p className="kicker">{"// matrix"}</p>
        <h2 className="title">Status in cubes.</h2>
        <p className="section-copy">
          Cubes are on or off — no fade. Loading orbits the rim; thinking
          rings in and out; tool is a smaller orbit; executing scans down;
          search scans across; compacting shrinks a filled square. Caution
          and error are static glyphs. Send a line below to see loading.
        </p>
        <CubeMatrixLegend />
      </section>
      <ChatbotThreadSpecimen />
      <ChatbotThreadSpecimen
        composerLayout="compact"
        kicker="// composer compact"
        heading="One row."
        copy="Attach on the left, field in the middle, send on the right. Same registry ComposerPrimitive — layout only. Type a line: the enter keycap fills, then click or Enter sends."
      />
      <ChatbotChromeSpecimen />
    </main>
  );
}
