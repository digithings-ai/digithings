import "./controls.css";
import { DropdownReference } from "@/components/controls/dropdown-reference";
import { NavButtonsReference } from "@/components/controls/nav-buttons-reference";
import { SearchBarReference } from "@/components/controls/search-bar-reference";

export default function ControlsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// controls"}</p>
        <h1>
          Inputs, <em>with states.</em>
        </h1>
        <p>
          The interactive atoms: dropdowns, search, wayfinding buttons and form fields — every one
          keyboard-reachable, wearing the accent on focus and the money/livery colors only where
          they mean something.
        </p>
      </header>

      <DropdownReference />
      <SearchBarReference />
      <NavButtonsReference />
    </main>
  );
}
