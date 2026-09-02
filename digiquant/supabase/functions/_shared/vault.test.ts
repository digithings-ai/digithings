/**
 * Vault vector + parseCredential + negative_cases tests (T3 / K3 public contract).
 * See also settings/settings.test.ts for end-to-end handler coverage.
 */

import {
  assertEquals,
  assertRejects,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  buildAad,
  EnvelopeAuthenticationError,
  fingerprint,
  hexToBytes,
  openBytes,
  parseCredential,
  sealBytesWithNonce,
  VaultKeyMismatchError,
  VaultPayloadError,
  type MasterKey,
} from "./vault.ts";

type VectorDoc = {
  keys: Record<string, { base64: string }>;
  vectors: Array<{
    name: string;
    key_id: string;
    nonce_hex: string;
    aad: string;
    plaintext_utf8: string;
    ciphertext_hex: string;
    fingerprint: string | null;
  }>;
  negative_cases: Array<{
    vector: string;
    mutation: string;
    detail: string;
    expect: string;
  }>;
};

async function loadVectors(): Promise<VectorDoc> {
  const raw = await Deno.readTextFile(new URL("./vault-vectors.json", import.meta.url));
  return JSON.parse(raw) as VectorDoc;
}

function masterKey(doc: VectorDoc, keyId: string): MasterKey {
  return {
    key_id: keyId,
    material: Uint8Array.from(
      atob(doc.keys[keyId]!.base64),
      (c) => c.charCodeAt(0),
    ),
  };
}

Deno.test("vault-vectors.json: all positive vectors round-trip", async () => {
  const doc = await loadVectors();

  for (const v of doc.vectors) {
    const key = masterKey(doc, v.key_id);
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

    if (v.plaintext_utf8.trimStart().startsWith("{") && v.fingerprint) {
      const cred = parseCredential(JSON.parse(v.plaintext_utf8));
      assertEquals(await fingerprint(cred), v.fingerprint, `${v.name} fingerprint`);
    }
  }
});

Deno.test("vault-vectors.json: negative_cases all fail closed", async () => {
  const doc = await loadVectors();
  const byName = new Map(doc.vectors.map((v) => [v.name, v]));

  for (const neg of doc.negative_cases) {
    const v = byName.get(neg.vector);
    if (!v) throw new Error(`unknown vector ${neg.vector}`);
    const sealed = {
      ciphertext: hexToBytes(v.ciphertext_hex),
      nonce: hexToBytes(v.nonce_hex),
      key_id: v.key_id,
    };
    let aad = new TextEncoder().encode(v.aad);
    let key = masterKey(doc, v.key_id);
    let envelope = { ...sealed, ciphertext: new Uint8Array(sealed.ciphertext) };

    switch (neg.mutation) {
      case "wrong_key": {
        // Same key_id label as the envelope, but v2 key *material* (K3 contract).
        // openBytes checks key_id match first — use v2 material under key_id=v1
        // so AES-GCM auth fails (authentication_failure), matching the vector detail.
        const v2 = masterKey(doc, "v2");
        key = { key_id: v.key_id, material: v2.material };
        break;
      }
      case "wrong_aad_workspace": {
        aad = new TextEncoder().encode(
          "22222222-2222-4222-8222-222222222222:alpaca:paper",
        );
        break;
      }
      case "wrong_aad_env": {
        aad = new TextEncoder().encode(
          "11111111-1111-4111-8111-111111111111:alpaca:live",
        );
        break;
      }
      case "truncated_ciphertext": {
        envelope = {
          ...envelope,
          ciphertext: envelope.ciphertext.slice(0, -1),
        };
        break;
      }
      case "flipped_tag_bit": {
        const ct = new Uint8Array(envelope.ciphertext);
        ct[ct.length - 1] ^= 0x01;
        envelope = { ...envelope, ciphertext: ct };
        break;
      }
      case "flipped_body_bit": {
        const ct = new Uint8Array(envelope.ciphertext);
        ct[0] ^= 0x01;
        envelope = { ...envelope, ciphertext: ct };
        break;
      }
      default:
        throw new Error(`unhandled mutation ${neg.mutation}`);
    }

    let threw: unknown = null;
    try {
      await openBytes(envelope, { aad, key });
    } catch (err) {
      threw = err;
    }
    if (threw === null) {
      throw new Error(`expected failure for ${neg.mutation}`);
    }
    // wrong_key with mismatched key_id would be VaultKeyMismatchError; our
    // mutation keeps key_id and swaps material → EnvelopeAuthenticationError.
    const ok =
      threw instanceof EnvelopeAuthenticationError ||
      threw instanceof VaultKeyMismatchError ||
      (threw instanceof Error && /auth|mismatch|truncat/i.test(String(threw)));
    assertEquals(ok, true, `${neg.mutation}: ${String(threw)}`);
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
    // Pass a real secret so the test actually asserts non-echo (not empty key_id alone).
    parseCredential({ kind: "api_key", key_id: "", secret });
  } catch (err) {
    assertEquals(err instanceof VaultPayloadError, true);
    assertEquals(String(err).includes(secret), false);
    return;
  }
  throw new Error("expected VaultPayloadError");
});

Deno.test("parseCredential rejects unknown keys (extra=forbid)", () => {
  try {
    parseCredential({
      kind: "api_key",
      key_id: "PK",
      secret: "s",
      extra_field: "nope",
    });
  } catch (err) {
    assertEquals(err instanceof VaultPayloadError, true);
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
