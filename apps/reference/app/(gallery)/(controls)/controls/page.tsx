import "./controls.css";
import { AccordionReference } from "@/components/controls/accordion-reference";
import { DialogReference } from "@/components/controls/dialog-reference";
import { DropdownReference } from "@/components/controls/dropdown-reference";
import { EmptyStatesReference } from "@/components/controls/empty-states-reference";
import { FormFieldsReference } from "@/components/controls/form-fields-reference";
import { KitSurfaceReference } from "@/components/controls/kit-surface-reference";
import { NavButtonsReference } from "@/components/controls/nav-buttons-reference";
import { SearchBarReference } from "@/components/controls/search-bar-reference";
import { SelectReference } from "@/components/controls/select-reference";
import { SkeletonReference } from "@/components/controls/skeleton-reference";
import { SliderReference } from "@/components/controls/slider-reference";
import { TagsInputReference } from "@/components/controls/tags-input-reference";
import { TooltipReference } from "@/components/controls/tooltip-reference";

/**
 * The one controls family. Every `@digithings/ui/ui` part has exactly one
 * canonical specimen here (the former `/ui` route folded in, #4306); see
 * `lib/specimen-inventory.ts` for the part → specimen map, pinned by
 * `lib/specimens.test.ts`.
 */
export default function ControlsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// controls"}</p>
        <h1>
          Inputs, <em>with states.</em>
        </h1>
        <p>
          Every interactive atom in one family: the kit&apos;s current surface — variants, tables,
          overlays, badges — plus the form, menu and wayfinding controls. All keyboard-reachable,
          wearing the accent on focus and the money/livery colors only where they mean something.
        </p>
      </header>

      <KitSurfaceReference />
      <FormFieldsReference />
      <SelectReference />
      <DropdownReference />
      <DialogReference />
      <TooltipReference />
      <AccordionReference />
      <SearchBarReference />
      <NavButtonsReference />
      <SliderReference />
      <TagsInputReference />
      <SkeletonReference />
      <EmptyStatesReference />
    </main>
  );
}
