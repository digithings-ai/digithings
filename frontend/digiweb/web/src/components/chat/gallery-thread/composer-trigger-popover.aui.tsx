"use client";

import { memo, useRef, type ComponentPropsWithoutRef, type FC } from "react";
import {
  ComposerPrimitive,
  unstable_defaultDirectiveFormatter,
  unstable_useTriggerPopoverScopeContext,
  type Unstable_DirectiveFormatter,
  type Unstable_TriggerItem,
} from "@assistant-ui/react";
import { cn } from "./cn";

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
  return (
    <ComposerPrimitive.Unstable_TriggerPopoverItems>
      {(items) => (
        <div
          data-slot="composer-trigger-popover-items"
          className="flex max-h-[min(50vh,22rem)] flex-col overflow-y-auto py-1"
          ref={(node) => {
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
              className="flex w-full cursor-pointer items-baseline justify-between gap-4 px-3 py-1.5 text-start outline-none outline-offset-[-1px] data-[highlighted]:outline data-[highlighted]:outline-1"
            >
              <span className="shrink-0 text-sm font-medium">{item.label}</span>
              {item.description ? (
                <span className="text-muted-foreground min-w-0 truncate text-right text-xs leading-tight">
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
      )}
    </ComposerPrimitive.Unstable_TriggerPopoverItems>
  );
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
      <Items emptyLabel={emptyItemsLabel} loadingLabel={loadingLabel} />
    </ComposerPrimitive.Unstable_TriggerPopover>
  );
};
ComposerTriggerPopoverImpl.displayName = "ComposerTriggerPopover";

export const ComposerTriggerPopover = memo(
  ComposerTriggerPopoverImpl,
) as FC<ComposerTriggerPopoverProps>;
