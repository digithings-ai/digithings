/**
 * Allowlisted digiquant-runner commands (issue #4761).
 * commands.json is the source of truth shared with the container image.
 */

export type ArgvStep = string[];

export type GatedStep = {
  argv: string[];
  when_arg?: string;
  equals?: string;
  /** Run only when this arg is non-empty. */
  when_arg_set?: string;
  /** Run only when this arg is missing or blank. Empty date uses this branch. */
  when_arg_empty?: string;
  /** Append args[name] as the final argv element. */
  append_arg?: string;
  /** Append UTC YYYY-MM-DD. Resolved in the container, not in this catalog. */
  append_utc_date?: boolean;
  /** Non-zero exit does not fail the job (GHA continue-on-error). */
  continue_on_error?: boolean;
  /** Run even after an earlier step failed (GHA if: always() / success()||failure()). */
  always?: boolean;
  /** Skip unless this path exists under the image workdir. */
  when_file?: string;
};

export type CommandStep = ArgvStep | GatedStep;

export type CommandSpec = {
  timeout_seconds: number;
  concurrency: string;
  code_ref: "main";
  alias_supabase?: boolean;
  market_backend?: "r2";
  /** Non-secret literals baked into the child env. Never put tokens here. */
  extra_env?: Record<string, string>;
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
