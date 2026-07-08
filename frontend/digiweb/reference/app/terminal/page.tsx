import "./terminal.css";
import { CodeReviewReference } from "@/components/code-review-reference";
import { CodeSampleReference } from "@/components/code-sample-reference";
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
      <CodeReviewReference />
      <CodeSampleReference />
    </main>
  );
}
