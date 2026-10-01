"use client"

/**
 * Sidebar — the shadcn (`base-lyra`) sidebar family, vendored into the kit and
 * adapted for app shells (the dashboard's spine). Local deltas from stock:
 *
 *   - **Adjustable.** Width is state (`width` / `defaultWidth`, clamped to
 *     `minWidth`..`maxWidth`) driven by `SidebarRail`, a keyboard-operable
 *     `separator` handle: drag it, arrow keys nudge 16px, Home/End jump to the
 *     bounds, double-click resets. Persistence is the app's job — the provider
 *     reports `onWidthChange` / `onOpenChange` and takes them back as props, so
 *     the kit stays storage-free (no cookie, unlike stock).
 *   - **In flow, not fixed.** The desktop panel is a sticky flex sibling of
 *     `SidebarInset`, so it can never cover content, and there is no offcanvas
 *     mode: collapse is `icon` (a rail) or `none`.
 *   - **Kit tokens.** Stock's `--sidebar-*` palette is mapped onto the kit's
 *     `surface` / `ink-soft` / `accent-weak` / `hair` tokens; no new variables,
 *     no colour literals. Flat: no shadows, no width transition.
 *   - `SidebarInset` is a plain `div` — the app owns its one `<main>` landmark.
 *   - `SidebarMenuSkeleton` takes a deterministic `width` (stock randomised it
 *     in render, which mismatches on hydration).
 *
 * Below `md` the same children render in a kit `Sheet` (scroll lock, focus
 * trap, Escape), so the panel body is written once.
 */
import * as React from "react"
import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { PanelLeftIcon } from "lucide-react"

import { cn } from "../lib/utils"
import { Button } from "./button"
import { Input } from "./input"
import { Separator } from "./separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "./sheet"
import { Skeleton } from "./skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip"

const SIDEBAR_WIDTH = 240
const SIDEBAR_MIN_WIDTH = 176
const SIDEBAR_MAX_WIDTH = 400
const SIDEBAR_WIDTH_ICON = 56
const SIDEBAR_WIDTH_MOBILE = "18rem"
const SIDEBAR_KEYBOARD_SHORTCUT = "b"
const SIDEBAR_NUDGE = 16
const MOBILE_QUERY = "(max-width: 767px)"

type SidebarContextProps = {
  state: "expanded" | "collapsed"
  open: boolean
  setOpen: (open: boolean) => void
  openMobile: boolean
  setOpenMobile: (open: boolean) => void
  isMobile: boolean
  toggleSidebar: () => void
  width: number
  setWidth: (width: number) => void
  resetWidth: () => void
  minWidth: number
  maxWidth: number
}

const SidebarContext = React.createContext<SidebarContextProps | null>(null)

function useSidebar() {
  const context = React.useContext(SidebarContext)
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider.")
  }
  return context
}

function subscribeMobile(cb: () => void) {
  const mql = window.matchMedia(MOBILE_QUERY)
  mql.addEventListener("change", cb)
  return () => mql.removeEventListener("change", cb)
}

/** `< md`, false on the server so the desktop tree prerenders. */
function useIsMobile() {
  return React.useSyncExternalStore(
    subscribeMobile,
    () => window.matchMedia(MOBILE_QUERY).matches,
    () => false
  )
}

type SidebarProviderProps = React.ComponentProps<"div"> & {
  defaultOpen?: boolean
  open?: boolean
  onOpenChange?: (open: boolean) => void
  /** Expanded width in px. */
  defaultWidth?: number
  width?: number
  onWidthChange?: (width: number) => void
  minWidth?: number
  maxWidth?: number
  /** Cmd/Ctrl+B toggles; pass `false` when the app owns that key. */
  keyboardShortcut?: boolean
}

function SidebarProvider({
  defaultOpen = true,
  open: openProp,
  onOpenChange,
  defaultWidth = SIDEBAR_WIDTH,
  width: widthProp,
  onWidthChange,
  minWidth = SIDEBAR_MIN_WIDTH,
  maxWidth = SIDEBAR_MAX_WIDTH,
  keyboardShortcut = true,
  className,
  style,
  children,
  ...props
}: SidebarProviderProps) {
  const isMobile = useIsMobile()
  const [openMobile, setOpenMobile] = React.useState(false)

  const clamp = React.useCallback(
    (w: number) => Math.min(maxWidth, Math.max(minWidth, Math.round(w))),
    [minWidth, maxWidth]
  )

  // Uncontrolled state; `open` / `width` props take over when given.
  const [openState, setOpenState] = React.useState(defaultOpen)
  const [widthState, setWidthState] = React.useState(() => defaultWidth)
  const open = openProp ?? openState
  const width = clamp(widthProp ?? widthState)

  const setOpen = React.useCallback(
    (value: boolean) => {
      setOpenState(value)
      onOpenChange?.(value)
    },
    [onOpenChange]
  )
  const setWidth = React.useCallback(
    (value: number) => {
      const next = clamp(value)
      setWidthState(next)
      onWidthChange?.(next)
    },
    [clamp, onWidthChange]
  )
  const resetWidth = React.useCallback(() => setWidth(defaultWidth), [setWidth, defaultWidth])

  const toggleSidebar = React.useCallback(() => {
    if (isMobile) setOpenMobile((o) => !o)
    else setOpen(!open)
  }, [isMobile, open, setOpen])

  React.useEffect(() => {
    if (!keyboardShortcut) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === SIDEBAR_KEYBOARD_SHORTCUT && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        toggleSidebar()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [keyboardShortcut, toggleSidebar])

  const state = open ? "expanded" : "collapsed"

  const contextValue = React.useMemo<SidebarContextProps>(
    () => ({
      state,
      open,
      setOpen,
      isMobile,
      openMobile,
      setOpenMobile,
      toggleSidebar,
      width,
      setWidth,
      resetWidth,
      minWidth,
      maxWidth,
    }),
    [state, open, setOpen, isMobile, openMobile, toggleSidebar, width, setWidth, resetWidth, minWidth, maxWidth]
  )

  return (
    <SidebarContext.Provider value={contextValue}>
      <div
        data-slot="sidebar-wrapper"
        style={
          {
            "--sidebar-width": `${width}px`,
            "--sidebar-width-icon": `${SIDEBAR_WIDTH_ICON}px`,
            ...style,
          } as React.CSSProperties
        }
        className={cn("group/sidebar-wrapper flex h-dvh w-full", className)}
        {...props}
      >
        {children}
      </div>
    </SidebarContext.Provider>
  )
}

function Sidebar({
  collapsible = "icon",
  className,
  children,
  dir,
  ...props
}: React.ComponentProps<"div"> & {
  /** `icon`: collapses to a rail. `none`: fixed panel, no collapse. */
  collapsible?: "icon" | "none"
}) {
  const { isMobile, state, openMobile, setOpenMobile } = useSidebar()

  if (isMobile) {
    return (
      <Sheet open={openMobile} onOpenChange={setOpenMobile}>
        <SheetContent
          dir={dir}
          data-sidebar="sidebar"
          data-slot="sidebar"
          data-mobile="true"
          showCloseButton={false}
          side="left"
          className="w-(--sidebar-width) max-w-[85vw] bg-surface p-0 text-ink-soft sm:max-w-[85vw]"
          style={{ "--sidebar-width": SIDEBAR_WIDTH_MOBILE } as React.CSSProperties}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Sidebar</SheetTitle>
            <SheetDescription>Navigation, status and account.</SheetDescription>
          </SheetHeader>
          <div className="flex h-full w-full flex-col">{children}</div>
        </SheetContent>
      </Sheet>
    )
  }

  const collapsed = collapsible === "icon" && state === "collapsed"

  return (
    <div
      data-slot="sidebar"
      data-state={collapsible === "none" ? "expanded" : state}
      data-collapsible={collapsed ? "icon" : ""}
      className={cn(
        "group peer sticky top-0 hidden h-dvh w-(--sidebar-width) shrink-0 border-e border-hair bg-surface text-ink-soft data-[collapsible=icon]:w-(--sidebar-width-icon) md:flex",
        className
      )}
      {...props}
    >
      <div data-sidebar="sidebar" data-slot="sidebar-inner" className="flex size-full min-w-0 flex-col">
        {children}
      </div>
    </div>
  )
}

function SidebarTrigger({ className, onClick, ...props }: React.ComponentProps<typeof Button>) {
  const { toggleSidebar } = useSidebar()

  return (
    <Button
      data-sidebar="trigger"
      data-slot="sidebar-trigger"
      variant="ghost"
      size="icon-sm"
      className={cn(className)}
      onClick={(event) => {
        onClick?.(event)
        toggleSidebar()
      }}
      {...props}
    >
      <PanelLeftIcon className="rtl:rotate-180" />
      <span className="sr-only">Toggle Sidebar</span>
    </Button>
  )
}

/**
 * The resize handle: an ARIA `separator` on the panel's inline-end edge.
 * Drag, arrow keys (±16px), Home/End (bounds), double-click (reset).
 */
function SidebarRail({ className, ...props }: React.ComponentProps<"div">) {
  const { width, setWidth, resetWidth, minWidth, maxWidth, state } = useSidebar()
  const ref = React.useRef<HTMLDivElement>(null)

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    const panel = ref.current?.closest<HTMLElement>('[data-slot="sidebar"]')
    if (!panel) return
    e.preventDefault()
    const target = e.currentTarget
    target.setPointerCapture(e.pointerId)
    const rtl = getComputedStyle(panel).direction === "rtl"
    const move = (ev: PointerEvent) => {
      const rect = panel.getBoundingClientRect()
      setWidth(rtl ? rect.right - ev.clientX : ev.clientX - rect.left)
    }
    const up = () => {
      target.removeEventListener("pointermove", move)
      target.removeEventListener("pointerup", up)
      target.removeEventListener("pointercancel", up)
    }
    target.addEventListener("pointermove", move)
    target.addEventListener("pointerup", up)
    target.addEventListener("pointercancel", up)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const rtl = getComputedStyle(e.currentTarget).direction === "rtl"
    const grow = rtl ? "ArrowLeft" : "ArrowRight"
    const shrink = rtl ? "ArrowRight" : "ArrowLeft"
    if (e.key === grow) setWidth(width + SIDEBAR_NUDGE)
    else if (e.key === shrink) setWidth(width - SIDEBAR_NUDGE)
    else if (e.key === "Home") setWidth(minWidth)
    else if (e.key === "End") setWidth(maxWidth)
    else return
    e.preventDefault()
  }

  if (state === "collapsed") return null

  return (
    <div
      ref={ref}
      data-sidebar="rail"
      data-slot="sidebar-rail"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize sidebar"
      aria-valuemin={minWidth}
      aria-valuemax={maxWidth}
      aria-valuenow={width}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
      onDoubleClick={resetWidth}
      className={cn(
        "absolute inset-y-0 -end-1 z-20 hidden w-2 cursor-col-resize touch-none outline-none after:absolute after:inset-y-0 after:start-1/2 after:w-px hover:after:bg-accent focus-visible:after:w-0.5 focus-visible:after:bg-accent md:block",
        className
      )}
      {...props}
    />
  )
}

/** The app's content column, beside the panel. Not a landmark — the app owns `<main>`. */
function SidebarInset({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-inset"
      className={cn("relative flex min-w-0 flex-1 flex-col bg-bg", className)}
      {...props}
    />
  )
}

function SidebarInput({ className, ...props }: React.ComponentProps<typeof Input>) {
  return (
    <Input
      data-slot="sidebar-input"
      data-sidebar="input"
      className={cn("h-8 w-full bg-bg shadow-none", className)}
      {...props}
    />
  )
}

function SidebarHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-header"
      data-sidebar="header"
      className={cn("flex flex-col gap-2 p-2", className)}
      {...props}
    />
  )
}

function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-footer"
      data-sidebar="footer"
      className={cn("flex flex-col gap-2 p-2", className)}
      {...props}
    />
  )
}

function SidebarSeparator({ className, ...props }: React.ComponentProps<typeof Separator>) {
  return (
    <Separator
      data-slot="sidebar-separator"
      data-sidebar="separator"
      className={cn("mx-2 w-auto bg-hair", className)}
      {...props}
    />
  )
}

function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-content"
      data-sidebar="content"
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-0 overflow-y-auto group-data-[collapsible=icon]:overflow-hidden",
        className
      )}
      {...props}
    />
  )
}

function SidebarGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-group"
      data-sidebar="group"
      className={cn("relative flex w-full min-w-0 flex-col p-2", className)}
      {...props}
    />
  )
}

function SidebarGroupLabel({
  className,
  render,
  ...props
}: useRender.ComponentProps<"div"> & React.ComponentProps<"div">) {
  return useRender({
    defaultTagName: "div",
    props: mergeProps<"div">(
      {
        className: cn(
          "flex h-7 shrink-0 items-center rounded-none px-2 font-mono text-[0.68rem] tracking-[0.12em] text-ink-mute uppercase outline-hidden group-data-[collapsible=icon]:hidden focus-visible:ring-1 focus-visible:ring-ring/50 [&>svg]:size-4 [&>svg]:shrink-0",
          className
        ),
      },
      props
    ),
    render,
    state: {
      slot: "sidebar-group-label",
      sidebar: "group-label",
    },
  })
}

function SidebarGroupAction({
  className,
  render,
  ...props
}: useRender.ComponentProps<"button"> & React.ComponentProps<"button">) {
  return useRender({
    defaultTagName: "button",
    props: mergeProps<"button">(
      {
        className: cn(
          "absolute top-1.5 end-3 flex aspect-square w-5 cursor-pointer items-center justify-center rounded-none p-0 text-ink-soft outline-hidden group-data-[collapsible=icon]:hidden after:absolute after:-inset-2 hover:bg-accent-weak hover:text-ink focus-visible:ring-1 focus-visible:ring-ring/50 disabled:cursor-not-allowed md:after:hidden [&>svg]:size-4 [&>svg]:shrink-0",
          className
        ),
      },
      props
    ),
    render,
    state: {
      slot: "sidebar-group-action",
      sidebar: "group-action",
    },
  })
}

function SidebarGroupContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-group-content"
      data-sidebar="group-content"
      className={cn("w-full text-xs", className)}
      {...props}
    />
  )
}

function SidebarMenu({ className, ...props }: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="sidebar-menu"
      data-sidebar="menu"
      className={cn("flex w-full min-w-0 flex-col gap-0", className)}
      {...props}
    />
  )
}

function SidebarMenuItem({ className, ...props }: React.ComponentProps<"li">) {
  return (
    <li
      data-slot="sidebar-menu-item"
      data-sidebar="menu-item"
      className={cn("group/menu-item relative", className)}
      {...props}
    />
  )
}

const sidebarMenuButtonVariants = cva(
  "peer/menu-button group/menu-button flex w-full cursor-pointer items-center gap-2 overflow-hidden rounded-none border-s-2 border-s-transparent p-2 text-start font-mono text-[0.78rem] text-ink-soft outline-hidden transition-colors group-has-data-[sidebar=menu-action]/menu-item:pe-8 group-data-[collapsible=icon]:size-8! group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-2! hover:bg-accent-weak hover:text-ink focus-visible:ring-1 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:cursor-not-allowed aria-disabled:opacity-50 data-active:border-s-accent data-active:bg-accent-weak data-active:text-ink [&_svg]:size-4 [&_svg]:shrink-0 [&>span:last-child]:truncate",
  {
    variants: {
      variant: {
        default: "",
        outline: "border border-hair bg-bg data-active:border-s-2",
      },
      size: {
        default: "h-7 max-md:h-9",
        sm: "h-6 max-md:h-9",
        lg: "h-10 group-data-[collapsible=icon]:p-0!",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function SidebarMenuButton({
  render,
  isActive = false,
  variant = "default",
  size = "default",
  tooltip,
  className,
  ...props
}: useRender.ComponentProps<"button"> &
  React.ComponentProps<"button"> & {
    isActive?: boolean
    /** Shown on the right only while the panel is collapsed to the icon rail. */
    tooltip?: string | React.ComponentProps<typeof TooltipContent>
  } & VariantProps<typeof sidebarMenuButtonVariants>) {
  const { isMobile, state } = useSidebar()
  const comp = useRender({
    defaultTagName: "button",
    props: mergeProps<"button">(
      {
        className: cn(sidebarMenuButtonVariants({ variant, size }), className),
      },
      props
    ),
    render: !tooltip ? render : <TooltipTrigger render={render} />,
    state: {
      slot: "sidebar-menu-button",
      sidebar: "menu-button",
      size,
      active: isActive,
    },
  })

  if (!tooltip) {
    return comp
  }

  const tooltipProps = typeof tooltip === "string" ? { children: tooltip } : tooltip

  return (
    <Tooltip>
      {comp}
      <TooltipContent
        side="right"
        align="center"
        hideArrow
        hidden={state !== "collapsed" || isMobile}
        {...tooltipProps}
      />
    </Tooltip>
  )
}

function SidebarMenuAction({
  className,
  render,
  showOnHover = false,
  ...props
}: useRender.ComponentProps<"button"> &
  React.ComponentProps<"button"> & {
    showOnHover?: boolean
  }) {
  return useRender({
    defaultTagName: "button",
    props: mergeProps<"button">(
      {
        className: cn(
          "absolute top-1 end-1 flex aspect-square w-5 cursor-pointer items-center justify-center rounded-none p-0 text-ink-soft outline-hidden group-data-[collapsible=icon]:hidden after:absolute after:-inset-2 hover:bg-accent-weak hover:text-ink focus-visible:ring-1 focus-visible:ring-ring/50 disabled:cursor-not-allowed md:after:hidden [&>svg]:size-4 [&>svg]:shrink-0",
          showOnHover &&
            "group-focus-within/menu-item:opacity-100 group-hover/menu-item:opacity-100 aria-expanded:opacity-100 md:opacity-0",
          className
        ),
      },
      props
    ),
    render,
    state: {
      slot: "sidebar-menu-action",
      sidebar: "menu-action",
    },
  })
}

function SidebarMenuBadge({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sidebar-menu-badge"
      data-sidebar="menu-badge"
      className={cn(
        "pointer-events-none absolute end-1 top-1 flex h-5 min-w-5 items-center justify-center rounded-none px-1 text-xs font-medium text-ink-soft tabular-nums select-none group-data-[collapsible=icon]:hidden peer-hover/menu-button:text-ink peer-data-active/menu-button:text-ink",
        className
      )}
      {...props}
    />
  )
}

function SidebarMenuSkeleton({
  className,
  showIcon = false,
  width = "70%",
  ...props
}: React.ComponentProps<"div"> & {
  showIcon?: boolean
  /** Text bar width; fixed by the caller so server and client agree. */
  width?: string
}) {
  return (
    <div
      data-slot="sidebar-menu-skeleton"
      data-sidebar="menu-skeleton"
      className={cn("flex h-7 items-center gap-2 rounded-none px-2", className)}
      {...props}
    >
      {showIcon && <Skeleton className="size-4 rounded-none" data-sidebar="menu-skeleton-icon" />}
      <Skeleton
        className="h-4 max-w-(--skeleton-width) flex-1"
        data-sidebar="menu-skeleton-text"
        style={{ "--skeleton-width": width } as React.CSSProperties}
      />
    </div>
  )
}

function SidebarMenuSub({ className, ...props }: React.ComponentProps<"ul">) {
  return (
    <ul
      data-slot="sidebar-menu-sub"
      data-sidebar="menu-sub"
      className={cn(
        "ms-4 flex min-w-0 flex-col gap-0 border-s border-hair ps-1 group-data-[collapsible=icon]:hidden",
        className
      )}
      {...props}
    />
  )
}

function SidebarMenuSubItem({ className, ...props }: React.ComponentProps<"li">) {
  return (
    <li
      data-slot="sidebar-menu-sub-item"
      data-sidebar="menu-sub-item"
      className={cn("group/menu-sub-item relative", className)}
      {...props}
    />
  )
}

function SidebarMenuSubButton({
  render,
  size = "md",
  isActive = false,
  className,
  ...props
}: useRender.ComponentProps<"a"> &
  React.ComponentProps<"a"> & {
    size?: "sm" | "md"
    isActive?: boolean
  }) {
  return useRender({
    defaultTagName: "a",
    props: mergeProps<"a">(
      {
        className: cn(
          "flex h-6 min-w-0 cursor-pointer items-center gap-2 overflow-hidden rounded-none border-s-2 border-s-transparent px-2 font-mono text-[0.74rem] text-ink-soft outline-hidden group-data-[collapsible=icon]:hidden hover:bg-accent-weak hover:text-ink focus-visible:ring-1 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:cursor-not-allowed aria-disabled:opacity-50 max-md:h-9 data-active:border-s-accent data-active:bg-accent-weak data-active:text-ink [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0",
          className
        ),
      },
      props
    ),
    render,
    state: {
      slot: "sidebar-menu-sub-button",
      sidebar: "menu-sub-button",
      size,
      active: isActive,
    },
  })
}

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarInset,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
  useSidebar,
}
