"use client";

/**
 * Dialog specimen — the canonical centered modal from `@digithings/ui/ui`
 * (stock kit), live. Sibling of Sheet (same @base-ui/react primitive as a
 * side panel): click the trigger, Escape or the scrim dismisses, focus traps
 * inside while open. The delete-confirm danger tint rides a call-site
 * `text-destructive` on the title; the controls-layer `tone` prop has no
 * kit counterpart yet (see the Task-1b gap list).
 */
import { useState } from "react";
import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@digithings/ui/ui";

export function DialogReference() {
  const [deleted, setDeleted] = useState(false);
  return (
    <section className="section-block">
      <p className="kicker">{"// dialog"}</p>
      <h2 className="title">One modal, centered.</h2>
      <p className="section-copy">
        <code>Dialog</code> from <code>@digithings/ui/ui</code> is the canonical centered
        overlay — the same stock kit part the product apps adopt. Focus traps while open;
        Escape and the scrim dismiss. A danger confirm tints its title at the call site.{" "}
        {deleted ? "Run deleted. " : ""}
        Click the trigger — then close it with the keyboard.
      </p>

      <div className="mt-[1.2rem]">
        <Dialog
          onOpenChange={(open) => {
            if (!open) setDeleted(false);
          }}
        >
          <DialogTrigger render={<Button variant="destructive" />}>
            Delete backtest run
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="text-destructive">Delete this backtest?</DialogTitle>
              <DialogDescription>
                The run leaves the library index. Saved tearsheets and the trade log are kept.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="ghost" />}>Cancel</DialogClose>
              <DialogClose render={<Button variant="destructive" onClick={() => setDeleted(true)} />}>
                Delete run
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </section>
  );
}
