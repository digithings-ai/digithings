/**
 * Secretless worker doubles, withheld by the Brief desk. The rule lives in one
 * place now (`packages/ui/src/lib/stub-payload.ts`) because this copy had drifted
 * into matching the fixture as substrings, which is what put a stub banner over a
 * live NAV block.
 */
import { isStubPayload as isStubEnvelope } from "../../../../packages/ui/src/lib/stub-payload";

export { isStubEnvelope };

export const STUB_READ = 'The official API returned a stub envelope, not a house-book read.';
