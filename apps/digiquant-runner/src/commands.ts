/**
 * Allowlisted digiquant-runner commands (issue #4761).
 * commands.json is the source of truth shared with the container image.
 */

export type ArgvStep = string[];

export type GatedStep = {
  argv: string[];
  when_arg?: string;
  equals?: string;
};

export type CommandStep = ArgvStep | GatedStep;

export type CommandSpec = {
  timeout_seconds: number;
  concurrency: string;
  code_ref: "main";
  alias_supabase?: boolean;
  market_backend?: "r2";
  env: string[];
  steps: CommandStep[];
  publish?: string[];
};

export function loadCommands(json: unknown): Record<string, CommandSpec> {
  if (typeof json !== "object" || json === null || Array.isArray(json)) {
    throw new Error("commands.json must be an object");
  }
  const out: Record<string, CommandSpec> = {};
  for (const [name, value] of Object.entries(json)) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new Error(`command ${name} is not an object`);
    }
    out[name] = value as CommandSpec;
  }
  return out;
}

export function assertKnownCommand(
  name: string,
  commands: Record<string, CommandSpec>,
): CommandSpec {
  const spec = commands[name];
  if (!spec) {
    throw new Error(`unknown command: ${name}`);
  }
  return spec;
}

export function isArgvStep(step: CommandStep): step is ArgvStep {
  return Array.isArray(step);
}
