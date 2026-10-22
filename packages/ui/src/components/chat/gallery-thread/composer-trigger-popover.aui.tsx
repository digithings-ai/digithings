"use client";

import { memo, useEffect, useRef, type ComponentPropsWithoutRef, type FC } from "react";
import {
  ComposerPrimitive,
  unstable_defaultDirectiveFormatter,
  unstable_useTriggerPopoverScopeContext,
  type Unstable_DirectiveFormatter,
  type Unstable_TriggerItem,
} from "@assistant-ui/react";
import { cn } from "./cn";
import { DotMatrix } from "../DotMatrix";
import { OverlayScrollbar } from "../overlay-scrollbar";

type IconComponent = FC<{ className?: string }>;

type DirectiveBehaviorProps = {
  /** Formatter used to serialize the selected item into composer text. */
  formatter?: Unstable_DirectiveFormatter | undefined;
  /** Called after the directive text has been inserted into the composer. */
  onInserted?: ((item: Unstable_TriggerItem) => void) | undefined;
};

type ActionBehaviorProps = {
  /** Formatter used to serialize the audit-trail chip (when `removeOnExecute` is false). */
  formatter?: Unstable_DirectiveFormatter | undefined;
  /** Invoked with the selected item at the moment of selection. */
  onExecute: (item: Unstable_TriggerItem) => void;
  /** If `true`, strip the trigger text from the composer after executing. @default false */
  removeOnExecute?: boolean | undefined;
};

type ComposerTriggerPopoverBaseProps = Omit<
  ComponentPropsWithoutRef<typeof ComposerPrimitive.Unstable_TriggerPopover>,
  "children"
> & {
  /**
   * Maps icon keys to components. Unused on the digichat skin (flat command
   * + description rows). Kept so adapter bundles can still pass `iconMap`.
   */
  iconMap?: Record<string, IconComponent>;
  fallbackIcon?: IconComponent;
  backLabel?: string;
  emptyCategoriesLabel?: string;
  /** Label shown when no items match. @default "No matching items" */
  emptyItemsLabel?: string;
  /** Label shown while an async adapter is resolving items. @default "Loading…" */
  loadingLabel?: string;
};

type ComposerTriggerPopoverProps = ComposerTriggerPopoverBaseProps &
  (
    | {
        directive: DirectiveBehaviorProps;
        action?: never;
      }
    | {
        action: ActionBehaviorProps;
        directive?: never;
      }
  );

type ItemsProps = {
  emptyLabel: string;
  loadingLabel: string;
};

const Items: FC<ItemsProps> = ({ emptyLabel, loadingLabel }) => {
  const { isLoading } = unstable_useTriggerPopoverScopeContext();
  const listRef = useRef<HTMLDivElement | null>(null);
  return (
    <ComposerPrimitive.Unstable_TriggerPopoverItems>
      {(items) => (
        <div className="relative min-h-0">
        <div
          data-slot="composer-trigger-popover-items"
          className="flex max-h-[min(50vh,22rem)] flex-col overflow-y-auto py-1"
          ref={(node) => {
            listRef.current = node;
            node
              ?.querySelector<HTMLElement>("[data-highlighted]")
              ?.scrollIntoView({ block: "nearest" });
          }}
        >
          {items.map((item, index) => (
            <ComposerPrimitive.Unstable_TriggerPopoverItem
              key={item.id}
              item={item}
              index={index}
              className="flex w-full cursor-pointer items-center gap-2 px-2 py-1 text-start text-sm outline-none"
            >
              {/* Same mark language as the composer menu: the highlighted
                  row gets the user-message chevron and shifts right. */}
              <span className="aui-menu-cursor" aria-hidden>
                <DotMatrix state="user" decorative className="size-3.5" />
              </span>
              <span className="shrink-0 font-medium">{item.label}</span>
              {item.description ? (
                <span className="text-muted-foreground ml-auto min-w-0 truncate text-end text-xs leading-tight">
                  {item.description}
                </span>
              ) : null}
            </ComposerPrimitive.Unstable_TriggerPopoverItem>
          ))}
          {items.length === 0 && (
            <div className="text-muted-foreground px-3 py-2 text-sm">
              {isLoading ? loadingLabel : emptyLabel}
            </div>
          )}
        </div>
        <OverlayScrollbar targetRef={listRef} width={6} />
        </div>
      )}
    </ComposerPrimitive.Unstable_TriggerPopoverItems>
  );
};

/**
 * Arrow-key handling for the picker.
 *
 * The composer textarea keeps focus while the picker is open, so the keys are
 * caught at document level (capture) rather than on the popover.
 *
 * It lives inside `Unstable_TriggerPopover` because the popover scope is the
 * only place that exposes the picker's own `close()`. A synthetic Escape
 * dispatched on `document` has `document` as its target, so it never reaches
 * the composer's own keydown handler and the picker stayed open (DIG-4599).
 */
const TriggerPopoverArrowKeys: FC = () => {
  const { open, close } = unstable_useTriggerPopoverScopeContext();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      const popover = document.querySelector<HTMLElement>(
        '[data-slot="composer-trigger-popover"]',
      );
      if (!popover) return;
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "ArrowRight") {
        // Same as Enter: submit the highlighted row.
        popover.querySelector<HTMLElement>("[data-highlighted]")?.click();
        return;
      }
      // Same as Escape: go back / close the picker, through the picker's own
      // scope. Upstream's Escape handler closes the popover the same way.
      close();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [open, close]);
  return null;
};

/**
 * Pre-built popover UI for a trigger-driven picker (mentions, slash commands).
 * digichat: flat list, no category drill-down, no per-row icons, composer width.
 */
const ComposerTriggerPopoverImpl: FC<ComposerTriggerPopoverProps> = ({
  emptyItemsLabel = "No matching items",
  loadingLabel = "Loading…",
  className,
  directive,
  action,
  iconMap: _iconMap,
  fallbackIcon: _fallbackIcon,
  backLabel: _backLabel,
  emptyCategoriesLabel: _emptyCategoriesLabel,
  ...props
}) => {
  const warnedRef = useRef(false);
  if (
    process.env.NODE_ENV !== "production" &&
    !warnedRef.current &&
    Boolean(directive) === Boolean(action)
  ) {
    warnedRef.current = true;
    console.warn(
      "[assistant-ui] ComposerTriggerPopover requires exactly one of `directive` or `action` props.",
    );
  }

  return (
    <ComposerPrimitive.Unstable_TriggerPopover
      data-slot="composer-trigger-popover"
      className={cn(
        "aui-composer-trigger-popover bg-popover text-popover-foreground absolute inset-x-0 bottom-full z-50 mb-1 w-full overflow-hidden rounded-none border",
        className,
      )}
      {...props}
    >
      {directive ? (
        <ComposerPrimitive.Unstable_TriggerPopover.Directive
          formatter={directive.formatter ?? unstable_defaultDirectiveFormatter}
          onInserted={directive.onInserted}
        />
      ) : action ? (
        <ComposerPrimitive.Unstable_TriggerPopover.Action
          formatter={action.formatter ?? unstable_defaultDirectiveFormatter}
          onExecute={action.onExecute}
          removeOnExecute={action.removeOnExecute}
        />
      ) : null}
      <TriggerPopoverArrowKeys />
      <Items emptyLabel={emptyItemsLabel} loadingLabel={loadingLabel} />
    </ComposerPrimitive.Unstable_TriggerPopover>
  );
};
ComposerTriggerPopoverImpl.displayName = "ComposerTriggerPopover";

export const ComposerTriggerPopover = memo(
  ComposerTriggerPopoverImpl,
) as FC<ComposerTriggerPopoverProps>;
