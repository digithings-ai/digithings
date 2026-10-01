/**
 * Source of truth for the digiquant.io homepage `#pricing` section (#1226):
 * three honest open-core tiers + the pricing FAQ. Copy approved by maintainer.
 * No invented usage caps or fake limits (EVOLUTION.md §10, anti-pattern #2).
 * The older two-card `_contact.ts` copy still backs the standalone `/contact`
 * route (follow-up: reconcile once managed pricing firms up).
 */

export type PricingTier = {
  id: "self" | "managed" | "enterprise";
  name: string;
  price: string;
  cadence?: string;
  desc: string;
  features: readonly string[];
  cta?: { label: string; email: string; subject: string };
  featured?: boolean;
};

import { DQ_CONTACT_EMAIL } from "./_nav";

export const CONTACT_EMAIL = DQ_CONTACT_EMAIL;
export const WAITLIST_SUBJECT = "Managed%20digiquant%20waitlist";
export const ENTERPRISE_SUBJECT = "digiquant%20enterprise";

export const PRICING_TIERS: readonly PricingTier[] = [
  {
    id: "self",
    name: "Self-hosted",
    price: "Free",
    cadence: "· MIT",
    desc: "Run the full stack on your own infrastructure with your own model keys.",
    features: ["All core services", "Bring your own key", "Community support"],
    // CTA: a GitHub link, rendered by components/start/pricing-strip.tsx.
  },
  {
    id: "managed",
    name: "Managed",
    price: "Coming soon",
    desc: "Hosted digiquant with managed upgrades and observability. In development.",
    features: ["Everything in Self-hosted", "Managed upgrades", "Hosted tracing (digismith)"],
    cta: { label: "Join the waitlist", email: CONTACT_EMAIL, subject: WAITLIST_SUBJECT },
    featured: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "Contact",
    desc: "Custom deployment, SLAs, and support for regulated environments.",
    features: ["Everything in Managed", "SLA + priority support", "Deployment assistance"],
    cta: { label: "Contact us", email: CONTACT_EMAIL, subject: ENTERPRISE_SUBJECT },
  },
] as const;

export const PRICING_FAQ: readonly { q: string; a: string }[] = [
  {
    q: "What do I need to self-host?",
    a: "A container runtime (or a Python environment) and access to an LLM — any LiteLLM-supported provider or a local model. The rest ships in the open-core stack.",
  },
  {
    q: "Which engine runs the backtests?",
    a: "An open-source event-driven engine runs every backtest and optimize. It ships inside the stack you self-host, so the source and its license terms sit in the repository with everything else.",
  },
  {
    q: "Do I bring my own model keys?",
    a: "Yes. Self-hosting uses your own provider keys (any LiteLLM-supported provider) or a local model; keys stay on your infrastructure.",
  },
  {
    q: "Are there usage limits?",
    a: "No artificial request caps on the self-hosted stack. Throughput is bounded only by your own infrastructure and provider limits.",
  },
] as const;
