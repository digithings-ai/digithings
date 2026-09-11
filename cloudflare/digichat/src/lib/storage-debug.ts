/** Log localStorage failures when `NEXT_PUBLIC_DIGICHAT_DEBUG_STORAGE=1`. */
export function logStorageFailure(scope: string, err: unknown): void {
  if (process.env.NEXT_PUBLIC_DIGICHAT_DEBUG_STORAGE === "1") {
    console.debug(`[digichat:storage:${scope}]`, err);
  }
}
