"use client";

/**
 * Dialog specimen — the shared centered modal from @digithings/web, live.
 * Sibling of Sheet (same @base-ui/react primitive as a side panel): click
 * the trigger, Escape or the scrim dismisses, focus traps inside while open.
 * `tone="danger"` tints the title for confirm/delete flows. Dress is
 * `.ctl-dialog-*` in the package overlay sheet — no call-site CSS here.
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
} from "@digithings/web";

export function DialogReference() {
  const [deleted, setDeleted] = useState(false);
  return (
    <section className="section-block">
      <p className="kicker">{"// dialog"}</p>
      <h2 className="title">One modal, centered.</h2>
      <p className="section-copy">
        <code>Dialog</code> from <code>@digithings/web</code> is the centered counterpart to{" "}
        <code>Sheet</code> — same part vocabulary, one new prop:{" "}
        <code>tone=&quot;danger&quot;</code> tints the title for confirm/delete flows. Focus
        traps while open; Escape and the scrim dismiss. {deleted ? "Run deleted. " : ""}
        Click the trigger — then close it with the keyboard.
      </p>

      <div className="mt-[1.2rem]">
        <Dialog
          onOpenChange={(open) => {
            if (!open) setDeleted(false);
          }}
        >
          <DialogTrigger render={<Button variant="danger" />}>
            Delete backtest run
          </DialogTrigger>
          <DialogContent tone="danger">
            <DialogHeader>
              <DialogTitle>Delete this backtest?</DialogTitle>
              <DialogDescription>
                The run leaves the library index. Saved tearsheets and the trade log are kept.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="ghost" />}>Cancel</DialogClose>
              <DialogClose render={<Button variant="danger" onClick={() => setDeleted(true)} />}>
                Delete run
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </section>
  );
}
