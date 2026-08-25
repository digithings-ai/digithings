import { describe, expect, it } from 'vitest';
import {
  CORPUS_KEY_KINDS,
  HOUSE_PROFILE_PIN,
  TYPED_CHROME_GAP_COPY,
  corpusKeyKind,
  isValidCorpusKey,
} from './house-chrome';

describe('house-chrome contracts (#2644)', () => {
  it('pins digithings house identity from migration 075 seed', () => {
    expect(HOUSE_PROFILE_PIN.profileKey).toBe('house');
    expect(HOUSE_PROFILE_PIN.isHouseDefault).toBe(true);
    expect(HOUSE_PROFILE_PIN.label).toBe('digithings house');
    expect(HOUSE_PROFILE_PIN.schemaVersion).toBe(1);
    expect(HOUSE_PROFILE_PIN.versionId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
  });

  it('accepts tenant-agnostic corpus keys only', () => {
    expect(CORPUS_KEY_KINDS).toEqual(['theme', 'asset', 'segment']);
    expect(isValidCorpusKey('theme:macro.rates')).toBe(true);
    expect(isValidCorpusKey('asset:spy')).toBe(true);
    expect(isValidCorpusKey('segment:us-equity')).toBe(true);
    expect(isValidCorpusKey('user:alice')).toBe(false);
    expect(isValidCorpusKey('theme:')).toBe(false);
    expect(corpusKeyKind('asset:ewt')).toBe('asset');
    expect(corpusKeyKind('profile:house')).toBeNull();
  });

  it('documents typed gaps without inventing copy for private tables', () => {
    expect(TYPED_CHROME_GAP_COPY.corpus_service_role_only).toMatch(/does not invent/);
    expect(TYPED_CHROME_GAP_COPY.profile_live_read_blocked).toMatch(/service_role/);
    expect(TYPED_CHROME_GAP_COPY.period_empty).toMatch(/empty evidence/);
  });
});
