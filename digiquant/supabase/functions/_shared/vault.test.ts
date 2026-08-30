/**
 * Vault vector + parseCredential tests (T3 / K3 public contract).
 * See also settings/settings.test.ts for end-to-end handler coverage.
 */

import {
  assertEquals,
  assertRejects,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  buildAad,
  fingerprint,
  hexToBytes,
  openBytes,
  parseCredential,
  sealBytesWithNonce,
  VaultPayloadError,
  type MasterKey,
} from "./vault.ts";

Deno.test("vault-vectors.json: all positive vectors round-trip", async () => {
  const raw = await Deno.readTextFile(new URL("./vault-vectors.json", import.meta.url));
  const doc = JSON.parse(raw) as {
    keys: Record<string, { base64: string }>;
    vectors: Array<{
      name: string;
      key_id: string;
      nonce_hex: string;
      aad: string;
      plaintext_utf8: string;
      ciphertext_hex: string;
      fingerprint: string;
      negative?: boolean;
    }>;
    negative_cases?: Array<{ name: string }>;
  };

  for (const v of doc.vectors) {
    const key: MasterKey = {
      key_id: v.key_id,
      material: Uint8Array.from(
        atob(doc.keys[v.key_id]!.base64),
        (c) => c.charCodeAt(0),
      ),
    };
    const sealed = await sealBytesWithNonce(
      new TextEncoder().encode(v.plaintext_utf8),
      {
        nonce: hexToBytes(v.nonce_hex),
        aad: new TextEncoder().encode(v.aad),
        key,
      },
    );
    const gotHex = [...sealed.ciphertext]
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    assertEquals(gotHex, v.ciphertext_hex, v.name);

    const opened = await openBytes(sealed, {
      aad: new TextEncoder().encode(v.aad),
      key,
    });
    assertEquals(new TextDecoder().decode(opened), v.plaintext_utf8);

    // Credential fingerprint applies only to JSON credential payloads (not raw_bytes_*).
    if (v.plaintext_utf8.trimStart().startsWith("{")) {
      const cred = parseCredential(JSON.parse(v.plaintext_utf8));
      assertEquals(await fingerprint(cred), v.fingerprint, `${v.name} fingerprint`);
    }
  }
});

Deno.test("buildAad rejects colon in components", () => {
  let threw = false;
  try {
    buildAad("a:b", "alpaca", "paper");
  } catch {
    threw = true;
  }
  assertEquals(threw, true);
});

Deno.test("parseCredential raises VaultPayloadError without secret echo", () => {
  const secret = "NEVER-IN-MESSAGE";
  try {
    parseCredential({ kind: "oauth", access_token: "" });
  } catch (err) {
    assertEquals(err instanceof VaultPayloadError, true);
    assertEquals(String(err).includes(secret), false);
    return;
  }
  throw new Error("expected VaultPayloadError");
});

Deno.test("wrong AAD fails closed", async () => {
  const key: MasterKey = {
    key_id: "v1",
    material: Uint8Array.from(
      atob("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="),
      (c) => c.charCodeAt(0),
    ),
  };
  const aad = buildAad("11111111-1111-4111-8111-111111111111", "alpaca", "paper");
  const sealed = await sealBytesWithNonce(
    new TextEncoder().encode('{"kind":"oauth","access_token":"t"}'),
    { nonce: new Uint8Array(12), aad, key },
  );
  await assertRejects(
    () =>
      openBytes(sealed, {
        aad: buildAad("11111111-1111-4111-8111-111111111111", "alpaca", "live"),
        key,
      }),
  );
});
