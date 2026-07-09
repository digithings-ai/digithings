"use client";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  GitHubGlyph,
  Input,
  Label,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@digithings/web";

/**
 * Controls layer — the shipped @digithings/web control atoms in their
 * reference dress, the primitives the marketing sites and digichat both
 * consume. Everything below is the promoted layer, not a local copy: Button
 * (primary/ghost/quiet/danger/icon + loading), Badge (the tier/tone pills),
 * Input + Label, a Card frame, and a Tooltip in its reference skin. The core
 * atoms wear the controls-core.css dress; the tooltip wears the
 * controls-overlay.css skin — so this one specimen keeps both shared sheets
 * (and the controls @source) live in the catalog. Dress is keyed off
 * data-slot/aria state in the shared CSS, so the call sites carry no styling.
 */
export function ControlsLayerReference() {
  return (
    <TooltipProvider>
      <section className="section-block">
        <p className="kicker">{"// controls layer"}</p>
        <h2 className="title">The shipped atoms, reference dress.</h2>
        <p className="section-copy">
          <code>Button</code>, <code>Badge</code>, <code>Card</code>, <code>Input</code>,{" "}
          <code>Label</code> and <code>Tooltip</code> from <code>@digithings/web</code> — the same
          primitives digichat re-exports under its chat dress. Here they wear the reference dress
          (the default), so the catalog demos exactly what ships. Behavior comes from{" "}
          <code>@base-ui/react</code>; every rule lives in the shared controls sheets.
        </p>

        <div className="mt-[1.4rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            button
          </p>
          <div className="flex flex-wrap items-center gap-[0.9rem]">
            <Button variant="primary">Deploy strategy</Button>
            <Button variant="ghost">Preview</Button>
            <Button variant="quiet">Cancel</Button>
            <Button variant="danger">Halt live</Button>
            <Button loading disabled>
              Backtesting…
            </Button>
            <Button variant="icon" aria-label="View on GitHub">
              <GitHubGlyph />
            </Button>
          </div>
        </div>

        <div className="mt-[1.4rem]">
          <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            badge
          </p>
          <div className="flex flex-wrap items-center gap-[0.6rem]">
            <Badge>neutral</Badge>
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
              <Label htmlFor="ctl-endpoint">DigiGraph base URL</Label>
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
