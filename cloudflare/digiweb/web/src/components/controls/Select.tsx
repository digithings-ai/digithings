/**
 * Select — the shared form select. Behavior comes from @base-ui/react's
 * Select (type-ahead, arrow-key travel, flip-aware positioning, aria
 * wiring); this file only skins it to the form-fields grammar (ff-input
 * trigger, surface popup, accent check on the picked item). All dress lives
 * in styles/controls-core.css (`.ctl-select*`, import once app-wide); this
 * file carries no Tailwind utilities, so no `@source` line is needed for it.
 *
 * Compose: Select > (SelectTrigger > SelectValue) + SelectPopup > SelectItem
 * (each with SelectItemText; picked rows also take SelectItemIndicator).
 * `placeholder` renders dim until a value is picked. SelectPopup takes
 * `positionerProps` for anchor placement; SelectTrigger takes
 * `showChevron={false}` when the caller supplies its own icon.
 */
import { Select as SelectPrimitive } from "@base-ui/react/select";
import type { ReactNode } from "react";

import { cxBase } from "./cx";

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m4 6 4 4 4-4" />
    </svg>
  );
}

export type SelectProps<Value, Multiple extends boolean | undefined = false> =
  SelectPrimitive.Root.Props<Value, Multiple>;
export type SelectTriggerProps = SelectPrimitive.Trigger.Props & {
  showChevron?: boolean;
};
export type SelectPopupProps = SelectPrimitive.Popup.Props & {
  positionerProps?: Omit<
    React.ComponentProps<typeof SelectPrimitive.Positioner>,
    "children"
  >;
};

export function Select<Value, Multiple extends boolean | undefined = false>({
  ...props
}: SelectPrimitive.Root.Props<Value, Multiple>) {
  return <SelectPrimitive.Root {...props} />;
}

export function SelectTrigger({
  className,
  showChevron = true,
  children,
  ...props
}: SelectTriggerProps) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cxBase("ctl-select", className)}
      {...props}
    >
      {children}
      {showChevron ? <ChevronDown /> : null}
    </SelectPrimitive.Trigger>
  );
}

export function SelectValue({ className, ...props }: SelectPrimitive.Value.Props) {
  return (
    <SelectPrimitive.Value
      data-slot="select-value"
      className={cxBase("ctl-select-value", className)}
      {...props}
    />
  );
}

export function SelectPopup({
  className,
  positionerProps,
  ...props
}: SelectPopupProps) {
  return (
    <SelectPrimitive.Positioner
      data-slot="select-positioner"
      className="ctl-select-positioner"
      {...positionerProps}
    >
      <SelectPrimitive.Popup
        data-slot="select-popup"
        className={cxBase("ctl-select-popup ctl-pop", className)}
        {...props}
      />
    </SelectPrimitive.Positioner>
  );
}

export function SelectItem({
  className,
  children,
  ...props
}: SelectPrimitive.Item.Props) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cxBase("ctl-select-item", className)}
      {...props}
    >
      <SelectPrimitive.ItemText data-slot="select-item-text" className="ctl-select-item-text">
        {children}
      </SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}

export function SelectItemIndicator({
  children,
  ...props
}: { children?: ReactNode } & Omit<
  React.ComponentProps<typeof SelectPrimitive.ItemIndicator>,
  "children"
>) {
  return (
    <SelectPrimitive.ItemIndicator
      data-slot="select-item-indicator"
      className="ctl-select-check"
      {...props}
    >
      {children ?? (
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m3.5 8.5 3 3 6-7" />
        </svg>
      )}
    </SelectPrimitive.ItemIndicator>
  );
}

export function SelectSeparator({ className, ...props }: SelectPrimitive.Separator.Props) {
  return (
    <SelectPrimitive.Separator
      data-slot="select-separator"
      className={cxBase("ctl-select-separator", className)}
      {...props}
    />
  );
}
