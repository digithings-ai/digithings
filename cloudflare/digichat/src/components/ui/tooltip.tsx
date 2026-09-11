"use client"

// Thin re-export of the shared @digithings/web Tooltip (#1419). The shared
// control's DEFAULT skin ("chat") is digichat's inverted bubble, Provider
// delay defaults to 0, and Content takes side/sideOffset/align/alignOffset
// with the arrow — a bare re-export keeps the rendered look identical.
// skin="reference" on TooltipContent stays available for the pending
// product ruling.

export {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@digithings/web"
