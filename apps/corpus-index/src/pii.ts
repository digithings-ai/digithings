/**
 * Mask identity before any text is embedded or stored.
 * Emails, phones and IBANs are replaced. Structured name lines are removed.
 * Vector metadata is an allowlist: customer identity never becomes a key.
 */

const EMAIL = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;

const IBAN = /\b[A-Z]{2}\d{2}(?:\s*[A-Z0-9]){11,30}\b/gi;

const PHONE =
  /(?:\+\d{1,3}|00\d{1,3})(?:[\s().-]*\d){7,14}\b|\(\d{2,5}\)[\s.-]*\d{3,4}[\s.-]*\d{3,4}\b/g;

const IDENTITY_LINE =
  /^(?:from|customer|owner|sender|name|contact|email|e-mail|phone|tel|mobile|iban)\s*:.*$/i;

export const METADATA_KEYS = [
  "source",
  "ticket_id",
  "article_id",
  "state",
  "group",
  "created_at",
  "updated_at",
  "lang",
  "url",
  "chunk",
  "model",
  "doc_id",
  "content",
] as const;

const ALLOWED = new Set<string>(METADATA_KEYS);

const FORBIDDEN_KEY = /email|phone|name|customer|from|sender|owner|iban|author/i;

export function containsRawIdentity(value: string): boolean {
  EMAIL.lastIndex = 0;
  IBAN.lastIndex = 0;
  PHONE.lastIndex = 0;
  return EMAIL.test(value) || IBAN.test(value) || PHONE.test(value);
}

export function maskPii(text: string): string {
  const lines = text.split("\n").filter((line) => !IDENTITY_LINE.test(line.trim()));
  return lines
    .join("\n")
    .replace(EMAIL, "[email]")
    .replace(IBAN, "[iban]")
    .replace(PHONE, "[phone]");
}

export function assertCleanMetadata(metadata: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(metadata)) {
    if (!ALLOWED.has(key) || FORBIDDEN_KEY.test(key)) {
      throw new Error("metadata_identity");
    }
    if (typeof value !== "string" && typeof value !== "number") {
      throw new Error("metadata_identity");
    }
    if (typeof value === "string" && containsRawIdentity(value)) {
      throw new Error("metadata_identity");
    }
    if (key === "url" && typeof value === "string" && value.includes("@")) {
      throw new Error("metadata_identity");
    }
  }
}
