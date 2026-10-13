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

const W = "[A-ZÄÖÜ][\\p{L}'’.-]+";
const NAME_RUN = `${W}(?:\\s+(?:von|van|de|zu)?\\s*${W}){0,2}`;

/** Quoted mail headers inline in a reply: `Von: Max Muster <…> Gesendet: …`. */
const MAIL_HEADER = new RegExp(
  `\\b(Von|From|An|To|Cc|Bcc|Reply-To|Antwort an)\\s*:\\s*[^\\n]*?(?=\\s(?:Von|From|An|To|Cc|Bcc|Gesendet|Sent|Datum|Date|Betreff|Subject)\\s*:|\\n|$)`,
  "gu",
);
const GREETING = new RegExp(
  `\\b(Hallo|Hi|Hello|Hey|Dear|Moin|Servus|Liebe[rs]?|Sehr geehrte[rs]?|Guten (?:Tag|Morgen|Abend))(\\s+(?:Frau|Herr|Hr\\.|Fr\\.|Mr\\.?|Mrs\\.?|Ms\\.?|Dr\\.))*\\s+(${NAME_RUN})`,
  "gu",
);
const CLOSING = new RegExp(
  `\\b(Grüßen|Grüße|Gruß|Gruss|Grüsse|regards|Regards|Cheers)([,!.]?)\\s+(${NAME_RUN})`,
  "gu",
);
const HONORIFIC = new RegExp(`\\b(Frau|Herr|Herrn|Hr\\.|Fr\\.|Mr\\.?|Mrs\\.?|Ms\\.?|Dr\\.)\\s+(${NAME_RUN})`, "gu");
const COMPANY = new RegExp(
  `(?:${W}\\s+){0,4}${W}\\s+(?:gGmbH|GmbH(?:\\s*&\\s*Co\\.?\\s*KG)?|AG|KG|e\\.\\s?V\\.|UG|mbH|Ltd\\.?|Inc\\.?|LLC|SE|eG)\\b`,
  "gu",
);
/** Signature-block contact details that the international PHONE pattern misses. */
const SLASH_PHONE = /(?:\+\d{1,3}\s?)?\(?0?\d{2,5}\)?\s?\/\s?\d[\d\s-]{2,}\d/g;
const NATIONAL_PHONE = /\b0\d{2,5}(?:\s?[/-]\s?|\s)\d{2,}(?:[\s-]\d{1,6})*\b/g;
const STREET = /\b[\p{L}.-]*(?:straße|strasse|str\.|weg|platz|allee|gasse|ring|damm|ufer|chaussee)\s*\d+\s?[a-z]?\b/giu;
const POSTCODE_CITY = /\b(?:D-|DE-)?\d{5}\s+[A-ZÄÖÜ][\p{L}-]+(?:\s(?:am|an der|im|bei)\s[A-ZÄÖÜ][\p{L}-]+)?/gu;
const WEBSITE = /\b(?:https?:\/\/)?www\.[^\s,;|]+/gi;

/** Words that look like names after a greeting/closing but are not. */
const NOT_NAMES = new Set(["Team", "Support", "Ihr", "Ihre", "Euer", "Eure", "Zusammen", "Alle", "Allerseits", "OCC", "Online", "Compliance", "Center"]);

function escapeRe(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Display names from header-like fields: `"Max Muster" <max@x.de>` → `Max Muster`. */
export function namesFrom(values: unknown[]): string[] {
  const out = new Set<string>();
  for (const value of values) {
    if (typeof value !== "string") continue;
    for (const part of value.split(/[,;]/)) {
      const name = part.replace(/<[^>]*>/g, "").replace(/["']/g, "").replace(EMAIL, "").trim();
      if (name.length < 3 || /^[\d\W]+$/.test(name)) continue;
      out.add(name);
      for (const token of name.split(/\s+/)) if (token.length >= 3 && /^\p{Lu}/u.test(token)) out.add(token);
    }
  }
  return [...out].sort((a, b) => b.length - a.length);
}

export function maskPii(text: string, names: string[] = []): string {
  const lines = text.split("\n").filter((line) => !IDENTITY_LINE.test(line.trim()));
  let out = lines
    .join("\n")
    .replace(EMAIL, "[email]")
    .replace(IBAN, "[iban]")
    .replace(PHONE, "[phone]")
    .replace(MAIL_HEADER, (_m, key: string) => `${key}: [name]`)
    .replace(WEBSITE, "[website]")
    .replace(STREET, "[address]")
    .replace(POSTCODE_CITY, "[address]")
    .replace(SLASH_PHONE, "[phone]")
    .replace(NATIONAL_PHONE, "[phone]");
  for (const name of names) {
    out = out.replace(new RegExp(`(?<![\\p{L}])${escapeRe(name)}(?![\\p{L}])`, "gu"), "[name]");
  }
  const keep = (lead: string, run: string) => {
    const first = run.split(/\s+/)[0] ?? "";
    return NOT_NAMES.has(first) ? `${lead}${run}` : `${lead}[name]`;
  };
  return out
    .replace(GREETING, (_m, g: string, h = "", run: string) => keep(`${g}${h ?? ""} `, run))
    .replace(CLOSING, (_m, c: string, p: string, run: string) => keep(`${c}${p} `, run))
    .replace(HONORIFIC, (_m, h: string, run: string) => keep(`${h} `, run))
    .replace(COMPANY, "[organization]");
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
