"use client"

// Thin re-export of the shared @digithings/web DropdownMenu (#1419). The
// shared control's DEFAULT skin ("chat") reproduces digichat's rendered
// look exactly (shadcn tokens translated per the #1403 reverse bridge), so
// a bare re-export is correct — no pin needed. skin="reference" on
// DropdownMenuContent stays available for the pending product ruling.

export {
  DropdownMenu,
  DropdownMenuPortal,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuCheckboxItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from "@digithings/web"
