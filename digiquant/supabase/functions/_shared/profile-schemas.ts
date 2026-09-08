/**
 * Server re-validation of InvestmentProfile / AssetPreferences /
 * PipelineSchedule / ExecutionPolicy v1.
 *
 * Imports the REAL digiquant/docs/schemas/*.v1.json files (Deno JSON import) —
 * no hand-transcribed TS duplicate that can drift from Python.
 */

import investmentProfileSchema from "../../../docs/schemas/investment_profile.v1.json" with {
  type: "json",
};
import assetPreferencesSchema from "../../../docs/schemas/asset_preferences.v1.json" with {
  type: "json",
};
import pipelineScheduleSchema from "../../../docs/schemas/pipeline_schedule.v1.json" with {
  type: "json",
};
import executionPolicySchema from "../../../docs/schemas/execution_policy.v1.json" with {
  type: "json",
};

export const INVESTMENT_PROFILE_V1 = investmentProfileSchema as SchemaNode;
export const ASSET_PREFERENCES_V1 = assetPreferencesSchema as SchemaNode;
export const PIPELINE_SCHEDULE_V1 = pipelineScheduleSchema as SchemaNode;
export const EXECUTION_POLICY_V1 = executionPolicySchema as SchemaNode;

export type FieldError = { path: string; message: string };

export type ValidationResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; errors: FieldError[] };

type SchemaNode = {
  type?: string;
  enum?: readonly string[];
  const?: unknown;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  default?: unknown;
  items?: SchemaNode;
  properties?: Record<string, SchemaNode>;
  additionalProperties?: boolean | SchemaNode;
  required?: readonly string[];
  $ref?: string;
  $defs?: Record<string, SchemaNode>;
};

function fail(path: string, message: string): FieldError {
  return { path, message };
}

function resolveRef(root: SchemaNode, schema: SchemaNode): SchemaNode {
  if (!schema.$ref) return schema;
  const match = /^#\/\$defs\/(.+)$/.exec(schema.$ref);
  if (!match) return schema;
  const resolved = root.$defs?.[match[1]!];
  return resolved ?? schema;
}

function validateNode(
  root: SchemaNode,
  schema: SchemaNode,
  value: unknown,
  path: string,
  errors: FieldError[],
): void {
  const resolved = resolveRef(root, schema);

  if (resolved.type === "object") {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      errors.push(fail(path, "must be an object"));
      return;
    }
    const obj = value as Record<string, unknown>;
    for (const req of resolved.required ?? []) {
      if (!(req in obj) || obj[req] === undefined) {
        errors.push(fail(path ? `${path}.${req}` : req, "required"));
      }
    }
    const props = resolved.properties ?? {};
    for (const key of Object.keys(obj)) {
      if (!(key in props)) {
        if (resolved.additionalProperties === false) {
          errors.push(fail(path ? `${path}.${key}` : key, "additional property not allowed"));
        } else if (
          typeof resolved.additionalProperties === "object" &&
          resolved.additionalProperties !== null
        ) {
          validateNode(
            root,
            resolved.additionalProperties,
            obj[key],
            path ? `${path}.${key}` : key,
            errors,
          );
        }
        continue;
      }
      validateNode(root, props[key]!, obj[key], path ? `${path}.${key}` : key, errors);
    }
    return;
  }

  if (resolved.type === "array") {
    if (!Array.isArray(value)) {
      errors.push(fail(path, "must be an array"));
      return;
    }
    if (resolved.items) {
      value.forEach((item, i) =>
        validateNode(root, resolved.items!, item, `${path}[${i}]`, errors)
      );
    }
    return;
  }

  if (resolved.type === "string") {
    if (typeof value !== "string") {
      errors.push(fail(path, "must be a string"));
      return;
    }
    if (resolved.const !== undefined && value !== resolved.const) {
      errors.push(fail(path, `must be ${JSON.stringify(resolved.const)}`));
    }
    if (resolved.enum && !(resolved.enum as readonly string[]).includes(value)) {
      errors.push(fail(path, `must be one of: ${resolved.enum.join(", ")}`));
    }
    if (resolved.pattern && !new RegExp(resolved.pattern).test(value)) {
      errors.push(fail(path, `must match ${resolved.pattern}`));
    }
    return;
  }

  if (resolved.type === "boolean") {
    if (typeof value !== "boolean") {
      errors.push(fail(path, "must be a boolean"));
    }
    return;
  }

  if (resolved.type === "integer") {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      errors.push(fail(path, "must be an integer"));
      return;
    }
    if (resolved.minimum !== undefined && value < resolved.minimum) {
      errors.push(fail(path, `must be >= ${resolved.minimum}`));
    }
    if (resolved.maximum !== undefined && value > resolved.maximum) {
      errors.push(fail(path, `must be <= ${resolved.maximum}`));
    }
  }
}

export function validateAgainstSchema(
  schema: SchemaNode,
  value: unknown,
): ValidationResult {
  const errors: FieldError[] = [];
  validateNode(schema, schema, value, "", errors);
  if (errors.length > 0) return { ok: false, errors };
  return { ok: true, value: value as Record<string, unknown> };
}

export function validateInvestmentProfile(value: unknown): ValidationResult {
  return validateAgainstSchema(INVESTMENT_PROFILE_V1, value);
}

export function validateAssetPreferences(value: unknown): ValidationResult {
  return validateAgainstSchema(ASSET_PREFERENCES_V1, value);
}

export function validatePipelineSchedule(value: unknown): ValidationResult {
  return validateAgainstSchema(PIPELINE_SCHEDULE_V1, value);
}

export function validateExecutionPolicy(value: unknown): ValidationResult {
  return validateAgainstSchema(EXECUTION_POLICY_V1, value);
}

/** Reserved house profile key — overlays must never claim it (fail closed). */
export const HOUSE_PROFILE_KEY = "house";
