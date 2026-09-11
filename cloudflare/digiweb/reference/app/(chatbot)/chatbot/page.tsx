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
          This page mounts the same first-party <code>Thread</code> as
          product <code>/embed</code> (<code>@digithings/web/chat/thread</code>)
          — welcome, messages, markdown, reasoning, MCP tools, composer — with a
          local fixture runtime, not a second registry copy. Shell: radius 0, monochrome
          ink. Welcome: official <code>components.Welcome</code> slot, in the
          footer immediately above the composer. Copy is
          deploy-config shaped (title + body). Optional example rows from
          config — not chips, not a top-of-thread empty state. Two composers:
          expanded (toolbar under the input) and
          compact (attach · field · send on one row). Send stays quiet until
          there is text, then fills. Enter and the send key both submit.
          Transcript: both roles left, cube marker on user and example
          rows, no assistant arrow, no bubbles. Waiting and chrome: 5×5 cube matrix,
          cubes snap on and off. Reasoning: hairline rail, no pill. A send
          streams website retrieval (<code>digisearch_query</code> then{" "}
          <code>digivault_get_note</code>) or a dashboard backtest (
          <code>digiquant_list_strategies</code> then{" "}
          <code>digiquant_run_backtest</code>). Theme toggle still flips
          light/dark.
        </p>
      </header>
      <section className="section-block" id="matrix">
        <p className="kicker">{"// matrix"}</p>
        <h2 className="title">Status in cubes.</h2>
        <p className="section-copy">
          Cubes are on or off — no fade. Loading sweeps a thick arc around
          the rim; thinking rings in and out; tool presses two bars together;
          executing scans down; search scans across; compacting shrinks a
          filled square. Thought is a light bulb. Caution, error, and every
          chat chrome mark (copy, send, roles) are static glyphs. Send a line
          below to see loading.
        </p>
        <CubeMatrixLegend />
      </section>
      <ChatbotThreadSpecimen />
      <ChatbotThreadSpecimen
        composerLayout="compact"
        kicker="// composer compact"
        heading="One row."
        copy="Attach on the left, field in the middle, send on the right. Same registry ComposerPrimitive — layout only. Empty and one typed line share height; a newline grows the field. Type a line: the enter keycap fills, then click or Enter sends."
      />
      <ChatbotChromeSpecimen />
    </main>
  );
}
