"use client";

import {
  GitHubGlyph,
  Spinner,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@digithings/ui";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@digithings/ui/ui";

/**
 * Controls layer — the shared control atoms the marketing sites and digichat
 * consume. Wave 3: Button (primary→default, ghost, quiet→outline,
 * danger→destructive, icon→ghost size=icon, loading→disabled+inline spinner),
 * Input + Label and the Card frame are the canonical kit parts
 * (`@digithings/ui/ui`). Wave 4: Badge joined the kit — W4-P1 added the
 * token-backed `neutral`/`accent`/`warn`/`up`/`down` tones, so this specimen
 * now renders the canonical kit chip (flat, not the old mono/uppercase
 * hairline `.ctl-badge-ref` dress). The reference-skin Tooltip stays on the
 * controls layer — the kit has no `skin` prop yet.
 */
export function ControlsLayerReference() {
  return (
    <TooltipProvider>
      <section className="section-block">
        <p className="kicker">{"// controls layer"}</p>
        <h2 className="title">The shipped atoms, reference dress.</h2>
        <p className="section-copy">
          <code>Button</code>, <code>Card</code>, <code>Input</code>, <code>Label</code> and{" "}
          <code>Badge</code> (neutral / accent / warn / up / down tones) from{" "}
          <code>@digithings/ui/ui</code> — the canonical kit. The reference-skin{" "}
          <code>Tooltip</code> still comes from <code>@digithings/ui</code>: the kit has no{" "}
          <code>skin</code> prop yet. Behavior comes from <code>@base-ui/react</code> either way.
        </p>

        <div className="mt-[1.4rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            button
          </p>
          <div className="flex flex-wrap items-center gap-[0.9rem]">
            <Button variant="default">Deploy strategy</Button>
            <Button variant="ghost">Preview</Button>
            <Button variant="outline">Cancel</Button>
            <Button variant="destructive">Halt live</Button>
            <Button disabled>
              <Spinner />
              Backtesting…
            </Button>
            <Button variant="ghost" size="icon" aria-label="View on GitHub">
              <GitHubGlyph />
            </Button>
          </div>
        </div>

        <div className="mt-[1.4rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            badge
          </p>
          <div className="flex flex-wrap items-center gap-[0.6rem]">
            <Badge variant="neutral">neutral</Badge>
            <Badge variant="accent">core</Badge>
            <Badge variant="warn">roadmap</Badge>
            <Badge variant="up">+2.4%</Badge>
            <Badge variant="down">−1.1%</Badge>
          </div>
        </div>

        <div className="mt-[1.4rem] grid gap-[1rem] sm:grid-cols-2">
          <div>
            <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
              input + label
            </p>
            <div className="flex flex-col gap-[0.4rem]">
              <Label htmlFor="ctl-endpoint">digigraph base URL</Label>
              <Input id="ctl-endpoint" type="url" placeholder="https://api.example.com" />
            </div>
          </div>

          <div>
            <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
              card
            </p>
            <Card>
              <CardHeader>
                <CardTitle>digigraph</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-[0.8rem] text-ink-soft">
                  The hairline-frame card — a header, body, and footer on the reference dress.
                </p>
              </CardContent>
              <CardFooter>
                <Badge variant="accent">core</Badge>
              </CardFooter>
            </Card>
          </div>
        </div>

        <div className="mt-[1.4rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            tooltip — reference skin
          </p>
          <Tooltip>
            <TooltipTrigger render={<Button variant="ghost" />}>Hover or focus me</TooltipTrigger>
            <TooltipContent skin="reference" side="top">
              Reference dress — surface pane, hair border, mono type.
            </TooltipContent>
          </Tooltip>
        </div>
      </section>
    </TooltipProvider>
  );
}
