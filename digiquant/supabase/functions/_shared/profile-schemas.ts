/**
 * Bundled InvestmentProfile / AssetPreferences v1 JSON schemas for server
 * re-validation (T3). Source of truth:
 *   digiquant/docs/schemas/{investment_profile,asset_preferences}.v1.json
 *
 * Keep field rules in sync with those files — do not invent a second schema.
 */

export const INVESTMENT_PROFILE_V1 = {
  type: "object",
  additionalProperties: false,
  required: [
    "risk_tolerance",
    "horizon_years",
    "liquidity_needs",
    "base_currency",
    "tax_jurisdiction",
    "esg_preference",
    "experience_level",
  ],
  properties: {
    schema_version: { type: "integer", minimum: 1, default: 1 },
    risk_tolerance: {
      type: "string",
      enum: ["conservative", "moderate", "aggressive"],
    },
    horizon_years: { type: "integer", minimum: 1, maximum: 50 },
    liquidity_needs: { type: "string", enum: ["low", "medium", "high"] },
    base_currency: { type: "string", pattern: "^[A-Z]{3}$" },
    tax_jurisdiction: { type: "string", enum: ["US", "EU", "UK", "CA", "AU", "OTHER"] },
    esg_preference: { type: "string", enum: ["none", "tilt", "strict"] },
    excluded_sectors: { type: "array", items: { type: "string" } },
    experience_level: {
      type: "string",
      enum: ["novice", "intermediate", "expert"],
    },
  },
} as const;

export const ASSET_PREFERENCES_V1 = {
  type: "object",
  additionalProperties: false,
  properties: {
    schema_version: { type: "integer", minimum: 1, default: 1 },
    watchlists: {
      type: "object",
      additionalProperties: { type: "array", items: { type: "string" } },
    },
    custom_universe: { type: "array", items: { type: "string" } },
    excluded_tickers: { type: "array", items: { type: "string" } },
    excluded_sectors: { type: "array", items: { type: "string" } },
  },
} as const;

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
