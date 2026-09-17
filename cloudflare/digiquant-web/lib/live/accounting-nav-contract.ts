/**
 * Fail-closed contract for digiquant.io live book NAV (#2599 / #3029).
 * Must match dashboard `lib/accounting-views.ts` view name — no client fallback.
 */

export const ACCOUNTING_NAV_VIEW = 'public_accounting_nav_history' as const;

export function isMissingPublicRelationError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const e = error as { code?: string; message?: string };
  if (e.code === 'PGRST205') return true;
  const msg = typeof e.message === 'string' ? e.message.toLowerCase() : '';
  return msg.includes('schema cache') || msg.includes('could not find the table');
}

export class AccountingNavContractError extends Error {
  readonly code = 'accounting_nav_contract' as const;
  readonly view = ACCOUNTING_NAV_VIEW;
  readonly causeError: unknown;

  constructor(causeError: unknown) {
    const detail =
      causeError && typeof causeError === 'object' && 'message' in causeError
        ? String((causeError as { message: unknown }).message)
        : causeError instanceof Error
          ? causeError.message
          : String(causeError ?? 'unknown error');
    const missing = isMissingPublicRelationError(causeError);
    super(
      missing
        ? `Accounting NAV contract failed: view "${ACCOUNTING_NAV_VIEW}" is missing ` +
            `(PostgREST PGRST205). Apply digiquant migrations 072–074 on the core ` +
            `Supabase project, then reload. Detail: ${detail}`
        : `Accounting NAV contract failed reading "${ACCOUNTING_NAV_VIEW}": ${detail}`,
    );
    this.name = 'AccountingNavContractError';
    this.causeError = causeError;
  }
}
