/**
 * Client-side InvestmentProfile / AssetPreferences validation (T3).
 * UX only — the settings Edge Function re-validates server-side.
 *
 * Schemas are bundled from digiquant/docs/schemas/*.v1.json.
 */

import investmentSchema from './schemas/investment_profile.v1.json';
import assetSchema from './schemas/asset_preferences.v1.json';

export type FieldError = { path: string; message: string };

export type ValidationResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; errors: FieldError[] };

type SchemaNode = {
  type?: string;
  enum?: string[];
  pattern?: string;
  minimum?: number;
  maximum?: number;
  items?: SchemaNode;
  properties?: Record<string, SchemaNode>;
  additionalProperties?: boolean | SchemaNode;
  required?: string[];
};

function validateNode(
  schema: SchemaNode,
  value: unknown,
  path: string,
  errors: FieldError[],
): void {
  if (schema.type === 'object') {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      errors.push({ path, message: 'must be an object' });
      return;
    }
    const obj = value as Record<string, unknown>;
    for (const req of schema.required ?? []) {
      if (!(req in obj) || obj[req] === undefined) {
        errors.push({ path: path ? `${path}.${req}` : req, message: 'required' });
      }
    }
    const props = schema.properties ?? {};
    for (const key of Object.keys(obj)) {
      if (!(key in props)) {
        if (schema.additionalProperties === false) {
          errors.push({
            path: path ? `${path}.${key}` : key,
            message: 'additional property not allowed',
          });
        } else if (
          typeof schema.additionalProperties === 'object' &&
          schema.additionalProperties
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
  if (schema.type === 'array') {
    if (!Array.isArray(value)) {
      errors.push({ path, message: 'must be an array' });
      return;
    }
    if (schema.items) {
      value.forEach((item, i) =>
        validateNode(schema.items!, item, `${path}[${i}]`, errors),
      );
    }
    return;
  }
  if (schema.type === 'string') {
    if (typeof value !== 'string') {
      errors.push({ path, message: 'must be a string' });
      return;
    }
    if (schema.enum && !schema.enum.includes(value)) {
      errors.push({ path, message: `must be one of: ${schema.enum.join(', ')}` });
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      errors.push({ path, message: `must match ${schema.pattern}` });
    }
    return;
  }
  if (schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isInteger(value)) {
      errors.push({ path, message: 'must be an integer' });
      return;
    }
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push({ path, message: `must be >= ${schema.minimum}` });
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push({ path, message: `must be <= ${schema.maximum}` });
    }
  }
}

function validate(schema: SchemaNode, value: unknown): ValidationResult {
  const errors: FieldError[] = [];
  validateNode(schema, value, '', errors);
  if (errors.length) return { ok: false, errors };
  return { ok: true, value: value as Record<string, unknown> };
}

/** Fields the UI always collects for InvestmentProfile (required by schema). */
export const INVESTMENT_REQUIRED = [
  'risk_tolerance',
  'horizon_years',
  'liquidity_needs',
  'base_currency',
  'tax_jurisdiction',
  'esg_preference',
  'experience_level',
] as const;

export function validateInvestmentProfile(value: unknown): ValidationResult {
  // Exported JSON schema omits `required`; enforce the product required set here.
  const withRequired: SchemaNode = {
    ...(investmentSchema as SchemaNode),
    required: [...INVESTMENT_REQUIRED],
  };
  return validate(withRequired, value);
}

export function validateAssetPreferences(value: unknown): ValidationResult {
  return validate(assetSchema as SchemaNode, value);
}

export const HOUSE_PROFILE_KEY = 'house';
