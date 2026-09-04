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
 * `placeholder` renders dim until a value is picked.
 */
import { Select as SelectPrimitive } from "@base-ui/react/select";
import type { ReactNode } from "react";

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

export function Select<Value, Multiple extends boolean | undefined = false>({
  ...props
}: SelectPrimitive.Root.Props<Value, Multiple>) {
  return <SelectPrimitive.Root {...props} />;
}

export function SelectTrigger({
  className,
  children,
  ...props
}: SelectPrimitive.Trigger.Props) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={className ? `ctl-select ${className}` : "ctl-select"}
      {...props}
    >
      {children}
      <ChevronDown />
    </SelectPrimitive.Trigger>
  );
}

export function SelectValue({ className, ...props }: SelectPrimitive.Value.Props) {
  return (
    <SelectPrimitive.Value
      data-slot="select-value"
      className={className ? `ctl-select-value ${className}` : "ctl-select-value"}
      {...props}
    />
  );
}

export function SelectPopup({ className, ...props }: SelectPrimitive.Popup.Props) {
  return (
    <SelectPrimitive.Positioner data-slot="select-positioner" className="ctl-select-positioner">
      <SelectPrimitive.Popup
        data-slot="select-popup"
        className={className ? `ctl-select-popup ctl-pop ${className}` : "ctl-select-popup ctl-pop"}
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
      className={className ? `ctl-select-item ${className}` : "ctl-select-item"}
      {...props}
    >
      <SelectPrimitive.ItemText data-slot="select-item-text" className="ctl-select-item-text">
        {children}
      </SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}

export function SelectItemIndicator({ children }: { children?: ReactNode }) {
  return (
    <SelectPrimitive.ItemIndicator data-slot="select-item-indicator" className="ctl-select-check">
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
      className={className ? `ctl-select-separator ${className}` : "ctl-select-separator"}
      {...props}
    />
  );
}
