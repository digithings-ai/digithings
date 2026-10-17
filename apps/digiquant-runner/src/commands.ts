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
  /** Cap this step at min(step_timeout_seconds, remaining job deadline). */
  step_timeout_seconds?: number;
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
  /** Relative path of the pipeline env file copied into the image. */
  pipeline_env?: string;
  /** Job args copied into the child as UPPER_SNAKE names. */
  export_args?: string[];
  /** Set GITHUB_RUN_ID to the runner run id so the chain checkpoint thread matches. */
  checkpoint_run_id?: boolean;
  /** Directory uploaded under pipeline-runs/<command>/<run_id>/. */
  publish_dir?: string;
  /** Publish that directory on success and on chain failure. */
  publish_always?: boolean;
  /** Arg whose value is an R2 prefix staged for the child as local paths. */
  stage_r2_prefix_arg?: string;
  env: string[];
  steps: CommandStep[];
  publish?: string[];
  /** Uploaded when the file exists. A missing path does not fail the job. */
  publish_if_present?: string[];
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
