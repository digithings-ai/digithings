import "./controls.css";
import { AccordionReference } from "@/components/controls/accordion-reference";
import { DropdownReference } from "@/components/controls/dropdown-reference";
import { EmptyStatesReference } from "@/components/controls/empty-states-reference";
import { FormFieldsReference } from "@/components/controls/form-fields-reference";
import { NavButtonsReference } from "@/components/controls/nav-buttons-reference";
import { SearchBarReference } from "@/components/controls/search-bar-reference";
import { SkeletonReference } from "@/components/controls/skeleton-reference";
import { SliderReference } from "@/components/controls/slider-reference";
import { TagsInputReference } from "@/components/controls/tags-input-reference";
import { TooltipReference } from "@/components/controls/tooltip-reference";

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
      <FormFieldsReference />
      <TooltipReference />
      <SliderReference />
      <TagsInputReference />
      <AccordionReference />
      <SkeletonReference />
      <EmptyStatesReference />
    </main>
  );
}
