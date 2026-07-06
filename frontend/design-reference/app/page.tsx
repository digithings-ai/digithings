import { ButtonsCtaReference } from "@/components/buttons-cta-reference";
import { DotMatrixStat } from "@/components/dot-matrix-stat";
import { LiverySwitcher } from "@/components/livery-switcher";
import { ScrollNavReference } from "@/components/scroll-nav-reference";
import { StrategySuiteReference } from "@/components/strategy-suite-reference";
import { TerminalBudgetReference } from "@/components/terminal-budget-reference";
import { WordRevealReference } from "@/components/word-reveal-reference";

export default function Home() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// frontend design reference"}</p>
        <h1>
          React <em>+ Tailwind + Motion</em> baseline.
        </h1>
        <p>
          Consolidated, app-native reference surface for frontend sections before migration into
          digithings-web, digiquant-web, and digichat.
        </p>
      </header>

      <LiverySwitcher />
      <DotMatrixStat />
      <ButtonsCtaReference />
      <ScrollNavReference />
      <StrategySuiteReference />
      <TerminalBudgetReference />
      <WordRevealReference />
    </main>
  );
}
