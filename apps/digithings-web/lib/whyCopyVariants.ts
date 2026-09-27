/**
 * The three why-band copy takes (A/B/C) as data. Review-only: the variants
 * page renders one full guided walk per version so the owner can scroll each
 * and pick. The live band (`WhyStack` + `whyStack`) stays untouched until a
 * version freezes in `why-band-copy.md` and migrates over.
 *
 * Versions share the specs, tags and captions — they differ in headline,
 * lede and walks, which is the comparison under review.
 */

import type { TourStep } from "@digithings/ui";
import { OWNED_TOUR_STEPS, RENTED_TOUR_STEPS } from "@/lib/whyStack";

export interface WhyCopyVersion {
  id: "A" | "B" | "C";
  name: string;
  blurb: string;
  headline: [string, string];
  lede: string;
  leftSteps: TourStep[];
  rightSteps: TourStep[];
}

const FULL_RENTED = ["app", "api", "model", "memory", "record", "oversight", "metal", "terms", "platform"];

const versionBLeft: TourStep[] = [
  {
    id: "surface",
    label: "You own one box. They own the rest.",
    line: "Your product sits on top. Everything it calls — the models, the index, the data, the machines — is somebody else's, and you reach it only through the shape they publish.",
    ids: ["app"],
  },
  {
    id: "interface",
    label: "One door in, and they hold the key.",
    line: "A single vendor interface is the only way through. Its limits, its version and its price are decided above you, on a schedule you do not set.",
    ids: ["app", "api"],
  },
  {
    id: "services",
    label: "Every layer below is rented by the meter.",
    line: "The model bills per token, the index per query, the data per gigabyte — three contracts, three meters, and nothing you can reach in to change.",
    ids: ["app", "api", "model", "memory", "record"],
  },
  {
    id: "no-exit",
    label: "No exit, only upgrades — theirs.",
    line: "Monitoring, machines and terms sit behind the same closed boundary — and the only direction is the vendor's next version, on their schedule, at their price.",
    ids: FULL_RENTED,
  },
];

const versionCLeft: TourStep[] = [
  {
    id: "surface",
    label: "You own one box. They own the rest.",
    line: "Your product sits on top. Everything it calls — the models, the index, the data, the machines — is somebody else's, and you reach it only through the shape they publish.",
    ids: ["app"],
  },
  {
    id: "interface",
    label: "One door in, and they hold the key.",
    line: "A single vendor interface is the only way through. Its limits, its version and its price are decided above you, on a schedule you do not set.",
    ids: ["app", "api"],
  },
  {
    id: "meters",
    label: "Every edge has a meter on it.",
    line: "The model bills per token, the index per query, the data per gigabyte — three contracts, three meters, and the meter runs whether the answer was worth it or not.",
    ids: ["app", "api", "model", "memory", "record"],
  },
  {
    id: "bill",
    label: "One bill, and you don't set it.",
    line: "Monitoring, machines and terms ride the same invoice. This is not a smaller stack than digithings — it is the same stack with every layer priced by someone else.",
    ids: FULL_RENTED,
  },
];

const versionBRight: TourStep[] = [
  {
    id: "overview",
    label: "Leave whenever — including piece by piece.",
    line: "Nothing here is a platform you marry. Every layer is a module you can run alone, so adoption starts with one box and never has to end with ten.",
    ids: [],
  },
  {
    id: "front",
    label: "Your front door, your router.",
    line: "digichat is the interface your product talks to; digigraph routes each request — chat, retrieval, or research — to the right module. Swap either without touching your product.",
    ids: ["chat", "graph"],
  },
  {
    id: "models",
    label: "Any model, no migration.",
    line: "digillm routes to whichever provider wins today. A better or cheaper model drops in behind the same call — no migration, no rewrite, no vendor's roadmap dictating yours.",
    ids: ["models"],
  },
  {
    id: "knowledge",
    label: "Your index, your vault, your stores.",
    line: "digisearch queries whatever backend you run; digivault keeps your notes addressable. Move stores without rewriting — the calls stay yours.",
    ids: ["memory", "vault"],
  },
  {
    id: "run",
    label: "Runs itself. Proves itself.",
    line: "digiclaw keeps the loop on schedule; digikey issues the keys; digismith traces every hop. Owning the stack is part of it — never being locked in is the point.",
    ids: ["claw", "keys", "traces"],
  },
];

const versionCRight: TourStep[] = [
  {
    id: "overview",
    label: "Same stack. No middleman.",
    line: "Your product calls an interface the same way it always did. Behind it, your keys call the providers directly and your hosts run the rest — the margin between them is gone.",
    ids: [],
  },
  {
    id: "models",
    label: "Any model, your rates.",
    line: "digillm routes to whichever provider wins today — model string, your key, your bill. When a cheaper model drops, you change a string, not a vendor.",
    ids: ["models"],
  },
  {
    id: "front",
    label: "Your front door, your router.",
    line: "digichat is the interface your product talks to; digigraph routes each request — chat, retrieval, or research — to the right module. Swap either without touching your product.",
    ids: ["chat", "graph"],
  },
  {
    id: "knowledge",
    label: "Your index, your vault.",
    line: "digisearch queries whatever backend you run; digivault keeps your notes addressable. Move stores without rewriting — the calls stay yours.",
    ids: ["memory", "vault"],
  },
  {
    id: "run",
    label: "Runs itself. Proves itself.",
    line: "digiclaw keeps the loop on schedule; digikey issues the keys; digismith traces every hop. Owning the stack is part of it — never being locked in is the point.",
    ids: ["claw", "keys", "traces"],
  },
];

export const WHY_COPY_VERSIONS: WhyCopyVersion[] = [
  {
    id: "A",
    name: "Compose it yourself",
    blurb: "Evolution of the live band, sharpened. Balanced across all four themes.",
    headline: ["Their AI stack,", "or the digithings stack you compose."],
    lede: "Off-the-shelf AI arrives as one fixed shape — models, index, data and machines behind a single interface, metered and versioned on somebody else's schedule. digithings is the same AI infrastructure as pieces you compose yourself: start with the layer that hurts, swap any piece without migrating, pay your provider's own rates. Owning the stack is part of it — never being locked in is the point.",
    leftSteps: RENTED_TOUR_STEPS,
    rightSteps: OWNED_TOUR_STEPS,
  },
  {
    id: "B",
    name: "Never locked in",
    blurb: "Freedom-first. The sharpest pain is the roadmap trap, not the bill.",
    headline: ["One vendor's roadmap,", "or your own stack, layer by layer."],
    lede: "Every off-the-shelf platform asks the same question: how much of your stack are you willing to rent back? digithings asks a different one: which layer do you want to take back first? Take the chat interface this quarter and the model gateway next — each piece runs on your hosts, your keys, your bill, and nothing you adopt locks the rest.",
    leftSteps: versionBLeft,
    rightSteps: versionBRight,
  },
  {
    id: "C",
    name: "No middleman's meter",
    blurb: "Price-first. The bill is the wedge for infra buyers.",
    headline: ["Metered by them,", "or priced by your own providers."],
    lede: "The managed AI bill is a margin on top of the same models, indexes and machines you could call directly. digithings removes the middleman's meter: your keys call the providers, your hosts run the rest, and every layer stays swappable when a cheaper option appears. Start with one module — each layer you take back is one less margin you pay.",
    leftSteps: versionCLeft,
    rightSteps: versionCRight,
  },
];
