/**
 * Server re-validation of InvestmentProfile / AssetPreferences v1.
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

export const INVESTMENT_PROFILE_V1 = investmentProfileSchema as SchemaNode;
export const ASSET_PREFERENCES_V1 = assetPreferencesSchema as SchemaNode;

export type FieldError = { path: string; message: string };

export type ValidationResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; errors: FieldError[] };

type SchemaNode = {
  type?: string;
  enum?: readonly string[];
  pattern?: string;
  minimum?: number;
  maximum?: number;
  default?: unknown;
  items?: SchemaNode;
  properties?: Record<string, SchemaNode>;
  additionalProperties?: boolean | SchemaNode;
  required?: readonly string[];
};

function fail(path: string, message: string): FieldError {
  return { path, message };
}

function validateNode(
  schema: SchemaNode,
  value: unknown,
  path: string,
  errors: FieldError[],
): void {
  if (schema.type === "object") {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      errors.push(fail(path, "must be an object"));
      return;
    }
    const obj = value as Record<string, unknown>;
    for (const req of schema.required ?? []) {
      if (!(req in obj) || obj[req] === undefined) {
        errors.push(fail(path ? `${path}.${req}` : req, "required"));
      }
    }
    const props = schema.properties ?? {};
    for (const key of Object.keys(obj)) {
      if (!(key in props)) {
        if (schema.additionalProperties === false) {
          errors.push(fail(path ? `${path}.${key}` : key, "additional property not allowed"));
        } else if (
          typeof schema.additionalProperties === "object" &&
          schema.additionalProperties !== null
        ) {
          validateNode(
            schema.additionalProperties,
            obj[key],
            path ? `${path}.${key}` : key,
            errors,
          );
        }
        continue;
      }
      validateNode(props[key]!, obj[key], path ? `${path}.${key}` : key, errors);
    }
    return;
  }

  if (schema.type === "array") {
    if (!Array.isArray(value)) {
      errors.push(fail(path, "must be an array"));
      return;
    }
    if (schema.items) {
      value.forEach((item, i) => validateNode(schema.items!, item, `${path}[${i}]`, errors));
    }
    return;
  }

  if (schema.type === "string") {
    if (typeof value !== "string") {
      errors.push(fail(path, "must be a string"));
      return;
    }
    if (schema.enum && !(schema.enum as readonly string[]).includes(value)) {
      errors.push(fail(path, `must be one of: ${schema.enum.join(", ")}`));
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      errors.push(fail(path, `must match ${schema.pattern}`));
    }
    return;
  }

  if (schema.type === "integer") {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      errors.push(fail(path, "must be an integer"));
      return;
    }
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(fail(path, `must be >= ${schema.minimum}`));
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(fail(path, `must be <= ${schema.maximum}`));
    }
  }
}

export function validateAgainstSchema(
  schema: SchemaNode,
  value: unknown,
): ValidationResult {
  const errors: FieldError[] = [];
  validateNode(schema, value, "", errors);
  if (errors.length > 0) return { ok: false, errors };
  return { ok: true, value: value as Record<string, unknown> };
}

export function validateInvestmentProfile(value: unknown): ValidationResult {
  return validateAgainstSchema(INVESTMENT_PROFILE_V1, value);
}

export function validateAssetPreferences(value: unknown): ValidationResult {
  return validateAgainstSchema(ASSET_PREFERENCES_V1, value);
}

/** Reserved house profile key — overlays must never claim it (fail closed). */
export const HOUSE_PROFILE_KEY = "house";
