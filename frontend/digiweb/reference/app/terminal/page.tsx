import "./terminal.css";
import { ChatMessage, ChatTranscript, TerminalStepCaret, TerminalWordmark } from "@digithings/web";
import { ChatResponseLoader } from "@/components/terminal/chat-response-loader";
import { CodeReviewReference } from "@/components/code-review-reference";
import { CodeSampleReference } from "@/components/code-sample-reference";
import { ContainerBootLoader } from "@/components/terminal/container-boot-loader";
import { StreamTranscriptReference } from "@/components/stream-transcript-reference";
import { TerminalBudgetReference } from "@/components/terminal-budget-reference";
import { TerminalManifestReference } from "@/components/terminal-manifest-reference";

export default function TerminalPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// terminal"}</p>
        <h1>
          The terminal, <em>inhabited.</em>
        </h1>
        <p>
          Diegetic CLI grammar: mono markers, scripted sessions, explicit illustrative budgets —
          the §05 frame that becomes the whole product in digichat.
        </p>
      </header>

      <TerminalBudgetReference />
      <TerminalManifestReference />
      <StreamTranscriptReference />

      <section className="section-block accent-digichat" id="container-boot-loader">
        <p className="kicker">{"// container-boot loader"}</p>
        <h2 className="title">The wait wears the mark.</h2>
        <p className="section-copy">
          A container that sleeps when idle answers its first request in 15–25 seconds, and a
          spinner spends all of it saying nothing. This says which phase is running, in the
          identity&apos;s own grammar: the step label types out at the blinking block cursor, holds
          long enough to read, deletes, and the next phase follows — the type-out the animated
          lockup uses to cycle module names, and the caret is literally{" "}
          <code>ChatStreamCursor</code>, not a redraw of it. No prompt mark before the label: word
          plus cursor <em>is</em> the lockup. The steps are a script — nothing can report progress
          from inside a container that has not started — so the last one holds rather than looping
          back to the first, which would read as stuck. One motion moment; reduced motion shows the
          first step whole with the caret still.
        </p>
        <div className="tl-stage">
          <ContainerBootLoader title={<TerminalWordmark suffix="chat" />} />
        </div>
      </section>

      <section className="section-block accent-digichat" id="module-loader">
        <p className="kicker">{"// module loader"}</p>
        <h2 className="title">One module waits; the family performs.</h2>
        <p className="section-copy">
          The default loader for any single module surface — a customer&apos;s embedded chat
          widget, a dashboard&apos;s cold boot — is the module&apos;s own lowercase name: it types
          in once, holds, and the block cursor keeps blinking beside it. No note, no erase, no
          cycling back to itself: a one-tenant wait is not a tour of the platform, so it does not
          perform one. This is <code>ContainerBootLoader</code> with a single, non-looping step —{" "}
          <code>{'steps={["digichat"]}'}</code> — same primitive as the boot loader above, just
          held on one word. Reduced motion renders the word whole from the first frame, caret
          still.
        </p>
        <div className="tl-stage">
          <ContainerBootLoader steps={["digichat"]} note={null} />
        </div>
        <p className="section-copy mt-[1.2rem]">
          The cycling <code>digi</code>-prefixed lockup is the exception, not the default: reserve
          it for a surface whose actual job is showing off the whole module family — the
          digithings.ai hero, an ecosystem splash — never a single product&apos;s own loading
          state. <code>digi</code> stays fixed; <code>TerminalStepCaret</code> types and erases
          each module suffix in turn at the house cadence.
        </p>
        <div className="tl-stage">
          <span className="font-mono text-[1.25rem] font-normal tracking-normal text-ink">
            digi
            <TerminalStepCaret
              steps={["chat", "graph", "quant", "search", "key", "vault"]}
              waitingLabel="Loading the module family…"
            />
          </span>
        </div>
      </section>

      <section className="section-block accent-digichat" id="chat-response-loader">
        <p className="kicker">{"// response loader"}</p>
        <h2 className="title">The turn starts before the answer does.</h2>
        <p className="section-copy">
          The same caret, in the gap between sending a message and the first token back. It
          occupies the assistant turn it is about to become — a <code>ChatMessage</code> row, so the{" "}
          <code>▸</code> marker, the grid and the body ink are the transcript&apos;s own and nothing
          shifts when the real turn replaces it. Faster than the boot loader on purpose: a long
          dwell here reads as a stall rather than as work. Pass the stream&apos;s stage events as{" "}
          <code>activeIndex</code> and the steps stop being a script; the caret erases and retypes
          on each one.
        </p>
        <ChatTranscript flat className="mt-[1.2rem] max-w-[640px] text-[0.78rem] leading-[2.1]">
          <ChatMessage role="user">size a kelly-capped BTC position at 2x leverage</ChatMessage>
          <ChatResponseLoader />
        </ChatTranscript>
      </section>

      <CodeReviewReference />
      <CodeSampleReference />
    </main>
  );
}
