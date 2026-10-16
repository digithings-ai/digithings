/**
 * Test-only helpers for license JWT fixtures. Generates an ephemeral RSA
 * keypair per test file and mints compact RS256 JWTs with `node:crypto` —
 * no fixtures on disk, no checked-in key material.
 */

import {
  createPrivateKey,
  createSign,
  generateKeyPairSync,
} from "node:crypto";

export interface TestKeypair {
  publicKeyPem: string;
  privateKeyPem: string;
}

export function generateTestKeypair(): TestKeypair {
  const { publicKey, privateKey } = generateKeyPairSync("rsa", {
    modulusLength: 2048,
  });
  return {
    publicKeyPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
    privateKeyPem: privateKey.export({ type: "pkcs8", format: "pem" }).toString(),
  };
}

function b64url(input: string | Buffer): string {
  const buf = typeof input === "string" ? Buffer.from(input, "utf8") : input;
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export function validLicensePayload(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  const now = Math.floor(Date.now() / 1000);
  return {
    iss: "http://127.0.0.1:8005",
    aud: "digichat-license",
    kind: "digichat-license",
    sub: "datatap",
    license_id: "lic-test-001",
    hosts: ["datatapstream.com"],
    iat: now,
    exp: now + 90 * 24 * 60 * 60,
    ...overrides,
  };
}

/** Mint a compact RS256 JWT for the given payload. */
export function mintLicenseJwt(
  privateKeyPem: string,
  payload: Record<string, unknown> = validLicensePayload(),
  header: Record<string, unknown> = { alg: "RS256", typ: "JWT" },
): string {
  const headerSeg = b64url(JSON.stringify(header));
  const payloadSeg = b64url(JSON.stringify(payload));
  const signer = createSign("RSA-SHA256");
  signer.update(`${headerSeg}.${payloadSeg}`, "utf8");
  const signature = signer.sign(createPrivateKey(privateKeyPem));
  return `${headerSeg}.${payloadSeg}.${b64url(signature)}`;
}
