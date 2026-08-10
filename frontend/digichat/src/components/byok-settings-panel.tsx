"use client";

import { useState } from "react";
import { Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ByokCliFlow } from "@/components/byok-cli-flow";
import { useBYOKKey } from "@/hooks/use-byok-key";

/**
 * Sheet / inline entry point for BYOK. The interactive flow is the shared
 * terminal ByokCliFlow (session-only keys + validation gate).
 */
export function BYOKSettingsPanel({ inline = false }: { inline?: boolean } = {}) {
  const {
    provider: storedProvider,
    model: storedModel,
    isSet,
    setKey,
    clearKey,
  } = useBYOKKey();

  const [open, setOpen] = useState(inline);

  const flow = (
    <ByokCliFlow
      onClose={inline ? () => undefined : () => setOpen(false)}
      onActivate={(key, provider, model) => {
        setKey(key, provider, model);
        if (!inline) setOpen(false);
      }}
      onClear={clearKey}
      active={isSet ? { provider: storedProvider, model: storedModel } : null}
    />
  );

  if (inline) {
    return (
      <div className="max-w-lg">
        <h3 className="mb-4 flex items-center gap-2 text-base font-semibold">
          <Key className="size-4" />
          Bring Your Own Key
        </h3>
        {flow}
      </div>
    );
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground"
            aria-label={isSet ? "BYOK key configured" : "Configure your own API key"}
          />
        }
      >
        <Key className="size-4" />
        <span className="hidden sm:inline">
          {isSet ? "BYOK" : "Use my key"}
        </span>
        {isSet && (
          <span className="ml-0.5 size-2 rounded-full bg-up" aria-hidden />
        )}
      </SheetTrigger>
      <SheetContent side="right" className="w-full max-w-md">
        <SheetHeader className="mb-6">
          <SheetTitle className="flex items-center gap-2 text-base font-semibold">
            <Key className="size-4" />
            Bring Your Own Key
          </SheetTitle>
        </SheetHeader>
        {open ? flow : null}
      </SheetContent>
    </Sheet>
  );
}
