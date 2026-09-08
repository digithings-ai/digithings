/** Contact tier copy for the standalone /contact route. */

export const CONTACT_SELF_FEATURES = [
  "The full research and portfolio-construction stack — execution is not built yet",
  "MIT-licensed; clone, fork, and run it on hardware you own",
  "Research, portfolio construction, and the backtest pipeline",
  "Your data, your machines, your keys — nothing leaves your infra",
  "Community support on GitHub",
] as const;

export const CONTACT_MANAGED_FEATURES = [
  "A hosted digiquant runner, operated for you — in development",
  "Onboarding and custom strategy setup",
  "Priority fixes and a say in the roadmap",
  "Optional on-prem / VPC deployment",
  "Everything in self-managed, kept running",
] as const;

export const MANAGED_CONTACT_EMAIL = "contact@digiquant.io";
export const MANAGED_CONTACT_SUBJECT = "Managed%20digiquant";
