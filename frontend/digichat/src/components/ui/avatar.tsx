"use client"

// Thin re-export of the shared @digithings/web Avatar family (#1419). The
// shared control has a single dress — digichat's current look, translated
// exactly — so no dress pin is needed (same @base-ui/react Avatar
// primitives underneath; sizes sm | default | lg).

export {
  Avatar,
  AvatarImage,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
  AvatarBadge,
} from "@digithings/web"
