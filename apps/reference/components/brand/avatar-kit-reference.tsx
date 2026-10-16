"use client";

import {
  Avatar,
  AvatarBadge,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
  AvatarImage,
} from "@digithings/ui/ui";

/**
 * Avatar specimen — the vendored stock shadcn avatar on Base UI, added to the
 * kit in batch K2. Every part: the image with a fallback while it loads (and
 * when it fails), the three sizes, the status badge, and a stacked group with
 * an overflow count. The images are the checked brand-Kit PNGs this page
 * already serves; the fallback reads `bg-muted`/`text-muted-foreground`.
 */
export function AvatarKitReference() {
  return (
    <div className="mt-[1.8rem] border-t border-hair pt-[1.4rem]" id="avatar-kit">
      <p className="kicker">{"// avatar kit"}</p>
      <h3 className="title">The part, not just the file.</h3>
      <p className="section-copy">
        <code>Avatar</code> from <code>@digithings/ui/ui</code> — the stock Base UI primitive with
        our tokens: image, fallback, status badge, sizes and a group. The PNGs above are the assets;
        this is the component that frames them.
      </p>

      <div className="mt-[1.2rem] flex flex-wrap items-center gap-[1.4rem]">
        <div className="flex items-center gap-[0.6rem]">
          <Avatar size="sm">
            <AvatarImage src="/brand/avatar/digithings-avatar-dark.png" alt="digithings, small" />
            <AvatarFallback>dg</AvatarFallback>
          </Avatar>
          <Avatar>
            <AvatarImage src="/brand/avatar/digithings-avatar-light.png" alt="digithings, default" />
            <AvatarFallback>dg</AvatarFallback>
          </Avatar>
          <Avatar size="lg">
            <AvatarImage src="/brand/avatar/digithings-avatar-dark.png" alt="digithings, large" />
            <AvatarFallback>dg</AvatarFallback>
          </Avatar>
        </div>

        <div className="flex items-center gap-[0.6rem]">
          <Avatar>
            {/* no accessible image — the fallback carries the initials */}
            <AvatarFallback>DG</AvatarFallback>
            <AvatarBadge />
          </Avatar>
          <span className="font-mono text-[0.72rem] text-ink-mute">fallback + badge</span>
        </div>

        <AvatarGroup>
          <Avatar>
            <AvatarImage src="/brand/avatar/digithings-avatar-dark.png" alt="digithings" />
            <AvatarFallback>dg</AvatarFallback>
          </Avatar>
          <Avatar>
            <AvatarImage src="/brand/avatar/digithings-avatar-light.png" alt="digithings" />
            <AvatarFallback>dg</AvatarFallback>
          </Avatar>
          <AvatarGroupCount>+5</AvatarGroupCount>
        </AvatarGroup>
      </div>
    </div>
  );
}
