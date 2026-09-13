/**
 * Client-side InvestmentProfile / AssetPreferences / PipelineSchedule /
 * ExecutionPolicy validation (T3).
 * UX only — the settings Edge Function re-validates server-side.
 *
 * Schemas are bundled from digiquant/docs/schemas/*.v1.json.
 */

import investmentSchema from './schemas/investment_profile.v1.json';
import assetSchema from './schemas/asset_preferences.v1.json';
import pipelineScheduleSchema from './schemas/pipeline_schedule.v1.json';
import executionPolicySchema from './schemas/execution_policy.v1.json';

export type FieldError = { path: string; message: string };

export type ValidationResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; errors: FieldError[] };

type SchemaNode = {
  type?: string;
  enum?: string[];
  const?: unknown;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  items?: SchemaNode;
  properties?: Record<string, SchemaNode>;
  additionalProperties?: boolean | SchemaNode;
  required?: string[];
  $ref?: string;
  $defs?: Record<string, SchemaNode>;
};

function resolveRef(root: SchemaNode, schema: SchemaNode): SchemaNode {
  if (!schema.$ref) return schema;
  const match = /^#\/\$defs\/(.+)$/.exec(schema.$ref);
  if (!match) return schema;
  return root.$defs?.[match[1]!] ?? schema;
}

function validateNode(
  root: SchemaNode,
  schema: SchemaNode,
  value: unknown,
  path: string,
  errors: FieldError[],
): void {
  const resolved = resolveRef(root, schema);
  if (resolved.type === 'object') {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      errors.push({ path, message: 'must be an object' });
      return;
    }
    const obj = value as Record<string, unknown>;
    for (const req of resolved.required ?? []) {
      if (!(req in obj) || obj[req] === undefined) {
        errors.push({ path: path ? `${path}.${req}` : req, message: 'required' });
      }
    }
    const props = resolved.properties ?? {};
    for (const key of Object.keys(obj)) {
      if (!(key in props)) {
        if (resolved.additionalProperties === false) {
          errors.push({
            path: path ? `${path}.${key}` : key,
            message: 'additional property not allowed',
          });
        } else if (
          typeof resolved.additionalProperties === 'object' &&
          resolved.additionalProperties
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
  if (resolved.type === 'array') {
    if (!Array.isArray(value)) {
      errors.push({ path, message: 'must be an array' });
      return;
    }
    if (resolved.items) {
      value.forEach((item, i) =>
        validateNode(root, resolved.items!, item, `${path}[${i}]`, errors),
      );
    }
    return;
  }
  if (resolved.type === 'string') {
    if (typeof value !== 'string') {
      errors.push({ path, message: 'must be a string' });
      return;
    }
    if (resolved.const !== undefined && value !== resolved.const) {
      errors.push({ path, message: `must be ${JSON.stringify(resolved.const)}` });
    }
    if (resolved.enum && !resolved.enum.includes(value)) {
      errors.push({ path, message: `must be one of: ${resolved.enum.join(', ')}` });
    }
    if (resolved.pattern && !new RegExp(resolved.pattern).test(value)) {
      errors.push({ path, message: `must match ${resolved.pattern}` });
    }
    return;
  }
  if (resolved.type === 'boolean') {
    if (typeof value !== 'boolean') {
      errors.push({ path, message: 'must be a boolean' });
    }
    return;
  }
  if (resolved.type === 'integer') {
    if (typeof value !== 'number' || !Number.isInteger(value)) {
      errors.push({ path, message: 'must be an integer' });
      return;
    }
    if (resolved.minimum !== undefined && value < resolved.minimum) {
      errors.push({ path, message: `must be >= ${resolved.minimum}` });
    }
    if (resolved.maximum !== undefined && value > resolved.maximum) {
      errors.push({ path, message: `must be <= ${resolved.maximum}` });
    }
  }
}

function validate(schema: SchemaNode, value: unknown): ValidationResult {
  const errors: FieldError[] = [];
  validateNode(schema, schema, value, '', errors);
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

export function validatePipelineSchedule(value: unknown): ValidationResult {
  return validate(pipelineScheduleSchema as SchemaNode, value);
}

export function validateExecutionPolicy(value: unknown): ValidationResult {
  return validate(executionPolicySchema as SchemaNode, value);
}

export const HOUSE_PROFILE_KEY = 'house';
