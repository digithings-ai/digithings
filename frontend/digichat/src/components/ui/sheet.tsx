"use client"

// Thin re-export of the shared @digithings/web Sheet (#1419). The shared
// control is a 1:1 prop-API match (side, showCloseButton, Header / Footer /
// Title / Description) and its single skin reproduces digichat's rendered
// look exactly, so a bare re-export is correct. SheetPortal / SheetOverlay
// exist upstream but were never exported here — surface kept identical.

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
} from "@digithings/web"
