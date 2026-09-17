"use client";

import {
  Badge,
  GitHubGlyph,
  Spinner,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@digithings/web";
import {
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from "@digithings/web/ui";

/**
 * Controls layer — the shared control atoms the marketing sites and digichat
 * consume. Wave 3: Button (primary→default, ghost, quiet→outline,
 * danger→destructive, icon→ghost size=icon, loading→disabled+inline spinner),
 * Input + Label and the Card frame are the canonical kit parts
 * (`@digithings/web/ui`). Badge (accent/warn/up/down tone labels) and the
 * reference-skin Tooltip stay on the controls layer — the kit carries neither
 * the semantic badge tones nor a `skin` prop yet (see the Task-1b gap list in
 * the wave-3 SDD dir). This specimen keeps the controls sheets live.
 */
export function ControlsLayerReference() {
  return (
    <TooltipProvider>
      <section className="section-block">
        <p className="kicker">{"// controls layer"}</p>
        <h2 className="title">The shipped atoms, reference dress.</h2>
        <p className="section-copy">
          <code>Button</code>, <code>Card</code>, <code>Input</code> and <code>Label</code> from{" "}
          <code>@digithings/web/ui</code> — the canonical kit. <code>Badge</code> (accent / warn /
          up / down tones) and the reference-skin <code>Tooltip</code> still come from{" "}
          <code>@digithings/web</code>: the kit carries neither the semantic badge tones nor a{" "}
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
