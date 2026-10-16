/**
 * TypeScript mirror of digiquant.vault.envelope public contract (K3).
 *
 * Python (`digiquant/src/digiquant/vault/envelope.py`) is the implementation of
 * record. This module must pass `_shared/vault-vectors.json` byte-for-byte before
 * writing any `broker_connections` row.
 *
 * Ingest surfaces MUST call `parseCredential` and must never log a raw
 * validation error — rejected input can echo secrets.
 *
 * Deploy of the settings function is blocked until K3 merges onto the deploy
 * target (see `settings/README.md`).
 */

export const MASTER_KEY_ENV = "DIGIQUANT_VAULT_MASTER_KEY";
export const KEY_ID_ENV = "DIGIQUANT_VAULT_KEY_ID";
export const DEFAULT_KEY_ID = "v1";
export const MASTER_KEY_BYTES = 32;
export const NONCE_BYTES = 12;
export const GCM_TAG_BYTES = 16;
export const MAX_PLAINTEXT_BYTES = 8192;
export const FINGERPRINT_HEX_CHARS = 8;

const KEY_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,31}$/;

export class VaultError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VaultError";
  }
}

export class VaultConfigurationError extends VaultError {
  constructor(message: string) {
    super(message);
    this.name = "VaultConfigurationError";
  }
}

export class VaultKeyMismatchError extends VaultError {
  constructor(message: string) {
    super(message);
    this.name = "VaultKeyMismatchError";
  }
}

export class EnvelopeAuthenticationError extends VaultError {
  constructor(message: string) {
    super(message);
    this.name = "EnvelopeAuthenticationError";
  }
}

export class VaultPayloadError extends VaultError {
  constructor(message: string) {
    super(message);
    this.name = "VaultPayloadError";
  }
}

export type MasterKey = {
  key_id: string;
  /** Raw 32-byte key material — never log or interpolate. */
  material: Uint8Array;
};

export type SealedEnvelope = {
  ciphertext: Uint8Array;
  nonce: Uint8Array;
  key_id: string;
};

export type OAuthCredential = {
  kind: "oauth";
  access_token: string;
  refresh_token?: string;
};

export type ApiKeyCredential = {
  kind: "api_key";
  key_id: string;
  secret: string;
};

export type BrokerCredential = OAuthCredential | ApiKeyCredential;

function envGet(
  source: Record<string, string> | undefined,
  key: string,
): string | undefined {
  if (source) return source[key];
  return Deno.env.get(key) ?? undefined;
}

export function loadMasterKey(
  source?: Record<string, string>,
): MasterKey {
  const raw = (envGet(source, MASTER_KEY_ENV) ?? "").trim();
  if (!raw) {
    throw new VaultConfigurationError(
      `${MASTER_KEY_ENV} is unset; the credential vault has no default key`,
    );
  }
  let material: Uint8Array;
  try {
    const bin = atob(raw);
    material = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  } catch {
    throw new VaultConfigurationError(
      `${MASTER_KEY_ENV} is not valid base64; expected ${MASTER_KEY_BYTES} bytes`,
    );
  }
  if (material.byteLength !== MASTER_KEY_BYTES) {
    throw new VaultConfigurationError(
      `${MASTER_KEY_ENV} decodes to ${material.byteLength} bytes; AES-256-GCM requires exactly ${MASTER_KEY_BYTES}`,
    );
  }
  const keyId = (envGet(source, KEY_ID_ENV) ?? DEFAULT_KEY_ID).trim();
  if (!KEY_ID_PATTERN.test(keyId)) {
    throw new VaultConfigurationError(
      `${KEY_ID_ENV} must match ${KEY_ID_PATTERN.source}`,
    );
  }
  return { key_id: keyId, material };
}

export function buildAad(workspaceId: string, broker: string, env: string): Uint8Array {
  for (const [name, value] of [
    ["workspace_id", workspaceId],
    ["broker", broker],
    ["env", env],
  ] as const) {
    if (typeof value !== "string" || !value.trim()) {
      throw new Error(`AAD component ${name} must be a non-empty string`);
    }
    if (value.includes(":")) {
      throw new Error(`AAD component ${name} must not contain ':'`);
    }
  }
  return new TextEncoder().encode(`${workspaceId}:${broker}:${env}`);
}

/**
 * Validate a raw mapping into a credential without leaking secrets on failure.
 * Mirrors Python `parse_credential` (Pydantic `extra="forbid"`) — MUST be used
 * at every ingest surface.
 */
export function parseCredential(raw: Record<string, unknown>): BrokerCredential {
  const kind = raw.kind;
  if (kind === "oauth") {
    const allowed = new Set(["kind", "access_token", "refresh_token"]);
    for (const key of Object.keys(raw)) {
      if (!allowed.has(key)) {
        throw new VaultPayloadError(
          "credential mapping is not a valid oauth/api_key payload",
        );
      }
    }
    const access = raw.access_token;
    if (typeof access !== "string" || access.length < 1 || access.length > 4096) {
      throw new VaultPayloadError(
        "credential mapping is not a valid oauth/api_key payload",
      );
    }
    const refresh = raw.refresh_token;
    if (refresh !== undefined && refresh !== null) {
      if (typeof refresh !== "string" || refresh.length < 1 || refresh.length > 4096) {
        throw new VaultPayloadError(
          "credential mapping is not a valid oauth/api_key payload",
        );
      }
      return { kind: "oauth", access_token: access, refresh_token: refresh };
    }
    return { kind: "oauth", access_token: access };
  }
  if (kind === "api_key") {
    const allowed = new Set(["kind", "key_id", "secret"]);
    for (const key of Object.keys(raw)) {
      if (!allowed.has(key)) {
        throw new VaultPayloadError(
          "credential mapping is not a valid oauth/api_key payload",
        );
      }
    }
    const keyId = raw.key_id;
    const secret = raw.secret;
    if (
      typeof keyId !== "string" ||
      keyId.length < 1 ||
      keyId.length > 256 ||
      typeof secret !== "string" ||
      secret.length < 1 ||
      secret.length > 4096
    ) {
      throw new VaultPayloadError(
        "credential mapping is not a valid oauth/api_key payload",
      );
    }
    return { kind: "api_key", key_id: keyId, secret };
  }
  throw new VaultPayloadError(
    "credential mapping is not a valid oauth/api_key payload",
  );
}

function secretMaterial(credential: BrokerCredential): string {
  return credential.kind === "oauth" ? credential.access_token : credential.secret;
}

/** Canonical JSON bytes matching Python `canonical_json` (sorted keys, no nulls). */
export function canonicalJson(credential: BrokerCredential): Uint8Array {
  let obj: Record<string, string>;
  if (credential.kind === "oauth") {
    obj = { access_token: credential.access_token, kind: "oauth" };
    if (credential.refresh_token) {
      obj.refresh_token = credential.refresh_token;
    }
  } else {
    obj = {
      key_id: credential.key_id,
      kind: "api_key",
      secret: credential.secret,
    };
  }
  const keys = Object.keys(obj).sort();
  const ordered: Record<string, string> = {};
  for (const k of keys) ordered[k] = obj[k]!;
  return new TextEncoder().encode(JSON.stringify(ordered));
}

export async function fingerprint(credential: BrokerCredential): Promise<string> {
  const data = new TextEncoder().encode(secretMaterial(credential));
  const digest = await crypto.subtle.digest("SHA-256", asBufferSource(data));
  const hex = [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return hex.slice(0, FINGERPRINT_HEX_CHARS);
}

/** Deno's BufferSource typing rejects SharedArrayBuffer-backed views — copy when needed. */
function asBufferSource(view: Uint8Array): ArrayBuffer {
  return view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength) as ArrayBuffer;
}

async function importAesKey(key: MasterKey): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    asBufferSource(key.material),
    { name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
}

export type SealOpts = { nonce: Uint8Array; aad: Uint8Array; key: MasterKey };
export type OpenOpts = { aad: Uint8Array; key?: MasterKey };
export type SealCredOpts = { aad: Uint8Array; key?: MasterKey };

/** Test-vector seal with a fixed nonce — production always uses `sealBytes`. */
export async function sealBytesWithNonce(
  plaintext: Uint8Array,
  opts: SealOpts,
): Promise<SealedEnvelope> {
  const { nonce, aad, key } = opts;
  if (plaintext.byteLength === 0) {
    throw new Error("plaintext must be non-empty bytes");
  }
  if (plaintext.byteLength > MAX_PLAINTEXT_BYTES) {
    throw new Error(`plaintext exceeds ${MAX_PLAINTEXT_BYTES} bytes`);
  }
  if (nonce.byteLength !== NONCE_BYTES) {
    throw new Error(`nonce must be exactly ${NONCE_BYTES} bytes`);
  }
  const cryptoKey = await importAesKey(key);
  const ct = await crypto.subtle.encrypt(
    {
      name: "AES-GCM",
      iv: asBufferSource(nonce),
      additionalData: asBufferSource(aad),
      tagLength: 128,
    },
    cryptoKey,
    asBufferSource(plaintext),
  );
  return {
    ciphertext: new Uint8Array(ct),
    nonce,
    key_id: key.key_id,
  };
}

export async function sealBytes(
  plaintext: Uint8Array,
  opts: SealCredOpts,
): Promise<SealedEnvelope> {
  const resolved = opts.key ?? loadMasterKey();
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_BYTES));
  return sealBytesWithNonce(plaintext, { nonce, aad: opts.aad, key: resolved });
}

export async function openBytes(
  envelope: SealedEnvelope,
  opts: OpenOpts,
): Promise<Uint8Array> {
  const resolved = opts.key ?? loadMasterKey();
  if (envelope.key_id !== resolved.key_id) {
    throw new VaultKeyMismatchError(
      `envelope was sealed under key_id=${envelope.key_id} but loaded key is ${resolved.key_id}`,
    );
  }
  try {
    const cryptoKey = await importAesKey(resolved);
    const pt = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: asBufferSource(envelope.nonce),
        additionalData: asBufferSource(opts.aad),
        tagLength: 128,
      },
      cryptoKey,
      asBufferSource(envelope.ciphertext),
    );
    return new Uint8Array(pt);
  } catch {
    throw new EnvelopeAuthenticationError(
      "sealed credential failed authentication (wrong master key, wrong workspace/broker/env binding, or altered ciphertext)",
    );
  }
}

export async function sealCredential(
  credential: BrokerCredential,
  opts: SealCredOpts,
): Promise<SealedEnvelope> {
  return sealBytes(canonicalJson(credential), opts);
}

/** Hex encode for Postgres bytea literals (`\\x…`). */
export function encodeBytea(raw: Uint8Array): string {
  return `\\x${[...raw].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
}

export function hexToBytes(hex: string): Uint8Array {
  if (hex.length % 2 !== 0) throw new Error("odd hex length");
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}
