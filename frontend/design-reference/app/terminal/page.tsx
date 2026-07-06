import "./terminal.css";
import { StreamTranscriptReference } from "@/components/stream-transcript-reference";
import { TerminalBudgetReference } from "@/components/terminal-budget-reference";

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
          the §05 frame that becomes the whole product in DigiChat.
        </p>
      </header>

      <TerminalBudgetReference />
      <StreamTranscriptReference />
    </main>
  );
}
