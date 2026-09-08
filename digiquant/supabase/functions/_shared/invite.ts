/**
 * Hashed product-invite redeem (FX Hub / 12x).
 *
 * Identity still comes from Supabase Auth (JWT). The invite is not a
 * login-optional passphrase — AUTH.md forbids client-side gates on a static
 * export. A high-entropy code, hashed at rest, inserts `client_product_grants`
 * for the caller's email and records an audit row for the operator.
 */

export const FX_HUB_PRODUCT = "fx_hub";
export const INVITE_ATTEMPT_WINDOW_MS = 60 * 60 * 1000;
export const INVITE_MAX_ATTEMPTS = 8;
export const INVITE_MIN_CODE_LENGTH = 10;

export type InviteCodeRow = {
  id: string;
  code_hash: string;
  max_redemptions: number | null;
  redemption_count: number;
  revoked_at: string | null;
};

export type InviteStore = {
  countAttempts(userId: string, sinceIso: string): Promise<number>;
  recordAttempt(row: {
    user_id: string;
    product_key: string;
    ok: boolean;
    attempted_at: string;
  }): Promise<void>;
  listActiveCodes(productKey: string): Promise<InviteCodeRow[]>;
  hasGrant(email: string, productKey: string): Promise<boolean>;
  insertGrant(email: string, productKey: string, note: string): Promise<void>;
  recordRedemption(row: {
    invite_code_id: string | null;
    product_key: string;
    user_id: string;
    email: string;
    source: "env" | "table";
    redeemed_at: string;
  }): Promise<void>;
  incrementRedemptionCount(id: string): Promise<void>;
  recordAdminAudit?(row: {
    workspace_id: string | null;
    event_key: string;
    sent_date: string;
    sent_at: string;
  }): Promise<void>;
};

export type RedeemOk = {
  ok: true;
  alreadyGranted: boolean;
  productKey: string;
};

export type RedeemErr = {
  ok: false;
  status: number;
  code: string;
  message: string;
};

export async function sha256Hex(plain: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(plain),
  );
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function timingSafeEqualHex(a: string, b: string): boolean {
  const left = a.trim().toLowerCase();
  const right = b.trim().toLowerCase();
  if (left.length === 0 || left.length !== right.length) return false;
  let acc = 0;
  for (let i = 0; i < left.length; i++) {
    acc |= left.charCodeAt(i) ^ right.charCodeAt(i);
  }
  return acc === 0;
}

export function normalizeInviteCode(raw: unknown): string {
  return typeof raw === "string" ? raw.trim() : "";
}

export function normalizeProductKey(raw: unknown): string {
  const key = typeof raw === "string" ? raw.trim().toLowerCase() : FX_HUB_PRODUCT;
  return key || FX_HUB_PRODUCT;
}

function invalid(): RedeemErr {
  return {
    ok: false,
    status: 403,
    code: "INVITE_INVALID",
    message: "Invite code is not valid.",
  };
}

export async function redeemProductInvite(args: {
  userId: string;
  email: string | null | undefined;
  productKey: unknown;
  code: unknown;
  envHash?: string | null;
  now?: Date;
  workspaceId?: string | null;
  store: InviteStore;
}): Promise<RedeemOk | RedeemErr> {
  const email = (args.email ?? "").trim().toLowerCase();
  if (!email || !email.includes("@")) {
    return {
      ok: false,
      status: 400,
      code: "EMAIL_REQUIRED",
      message: "Sign in with an account that has an email before redeeming an invite.",
    };
  }

  const productKey = normalizeProductKey(args.productKey);
  if (productKey !== FX_HUB_PRODUCT) {
    return {
      ok: false,
      status: 400,
      code: "UNKNOWN_PRODUCT",
      message: "Unknown product.",
    };
  }

  const code = normalizeInviteCode(args.code);
  if (code.length < INVITE_MIN_CODE_LENGTH) {
    return invalid();
  }

  const now = args.now ?? new Date();
  const since = new Date(now.getTime() - INVITE_ATTEMPT_WINDOW_MS).toISOString();
  const attempts = await args.store.countAttempts(args.userId, since);
  if (attempts >= INVITE_MAX_ATTEMPTS) {
    return {
      ok: false,
      status: 429,
      code: "INVITE_RATE_LIMIT",
      message: "Too many invite attempts. Try again later.",
    };
  }

  const presented = await sha256Hex(code);
  const envHash = (args.envHash ?? "").trim().toLowerCase();
  let matched: { id: string | null; source: "env" | "table" } | null = null;

  if (envHash && timingSafeEqualHex(presented, envHash)) {
    matched = { id: null, source: "env" };
  } else {
    const rows = await args.store.listActiveCodes(productKey);
    for (const row of rows) {
      if (row.revoked_at) continue;
      if (
        row.max_redemptions != null &&
        row.redemption_count >= row.max_redemptions
      ) {
        continue;
      }
      if (timingSafeEqualHex(presented, row.code_hash)) {
        matched = { id: row.id, source: "table" };
        break;
      }
    }
  }

  await args.store.recordAttempt({
    user_id: args.userId,
    product_key: productKey,
    ok: matched != null,
    attempted_at: now.toISOString(),
  });

  if (!matched) return invalid();

  const already = await args.store.hasGrant(email, productKey);
  if (already) {
    return { ok: true, alreadyGranted: true, productKey };
  }

  await args.store.insertGrant(
    email,
    productKey,
    "redeemed via hashed product invite",
  );
  await args.store.recordRedemption({
    invite_code_id: matched.id,
    product_key: productKey,
    user_id: args.userId,
    email,
    source: matched.source,
    redeemed_at: now.toISOString(),
  });
  if (matched.id) {
    await args.store.incrementRedemptionCount(matched.id);
  }

  const sentDate = now.toISOString().slice(0, 10);
  try {
    await args.store.recordAdminAudit?.({
      workspace_id: args.workspaceId ?? null,
      event_key: "fx_hub_invite_redeemed",
      sent_date: sentDate,
      sent_at: now.toISOString(),
    });
  } catch {
    // Audit is best-effort — grant already landed.
  }

  return { ok: true, alreadyGranted: false, productKey };
}
