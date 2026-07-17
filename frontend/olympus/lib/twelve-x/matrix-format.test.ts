import { describe, expect, it } from 'vitest';
import { directionStyle, directionBucket, formatTargets, convictionOpacity } from './matrix-format';

describe('matrix-format', () => {
  describe('directionBucket', () => {
    it('maps bullish synonyms → bull', () => {
      for (const d of ['bullish', 'Long', 'BUY']) expect(directionBucket(d)).toBe('bull');
    });
    it('maps bearish synonyms → bear', () => {
      for (const d of ['bearish', 'short', 'Sell']) expect(directionBucket(d)).toBe('bear');
    });
    it('maps watch → watch and anything else → neutral', () => {
      expect(directionBucket('watch')).toBe('watch');
      expect(directionBucket('neutral')).toBe('neutral');
      expect(directionBucket('')).toBe('neutral');
    });
  });

  describe('directionStyle', () => {
    it('gives green ▲ for bullish, red ▼ for bearish, amber ◆ for watch', () => {
      expect(directionStyle('bullish')).toMatchObject({ text: 'text-up', glyph: '▲' });
      expect(directionStyle('short')).toMatchObject({ text: 'text-down', glyph: '▼' });
      expect(directionStyle('watch')).toMatchObject({ text: 'text-warn', glyph: '◆' });
      expect(directionStyle('mixed')).toMatchObject({ text: 'text-ink-soft', glyph: '•' });
    });

    it('includes semantic-preserving hover classes for each direction', () => {
      // Bullish: hover should brighten the same up-themed background/border, never switch to accent.
      const bull = directionStyle('bullish');
      expect(bull.hoverBg).toContain('hover:bg-up');
      expect(bull.hoverBorder).toContain('hover:border-up');
      expect(bull.hoverBg).not.toContain('accent');
      expect(bull.hoverBorder).not.toContain('accent');

      // Bearish: hover should brighten the same down-themed background/border.
      const bear = directionStyle('bearish');
      expect(bear.hoverBg).toContain('hover:bg-down');
      expect(bear.hoverBorder).toContain('hover:border-down');

      // Watch: hover should brighten the same warn-themed background/border.
      const watch = directionStyle('watch');
      expect(watch.hoverBg).toContain('hover:bg-warn');
      expect(watch.hoverBorder).toContain('hover:border-warn');

      // Neutral: hover should brighten the same ink-themed background/border.
      const neutral = directionStyle('neutral');
      expect(neutral.hoverBg).toContain('hover:bg-ink');
      expect(neutral.hoverBorder).toContain('hover:border-');
    });
  });

  describe('convictionOpacity', () => {
    it('high=1, medium=0.85, low=0.65, unknown=0.78', () => {
      expect(convictionOpacity('high')).toBe(1);
      expect(convictionOpacity('Medium')).toBe(0.85);
      expect(convictionOpacity('low')).toBe(0.65);
      expect(convictionOpacity('')).toBe(0.78);
    });
  });

  describe('formatTargets', () => {
    it('returns null for empty/undefined', () => {
      expect(formatTargets(undefined)).toBeNull();
      expect(formatTargets([])).toBeNull();
    });
    it('joins strings/numbers and label+level objects', () => {
      expect(formatTargets(['1.10', 1.05])).toBe('1.10, 1.05');
      expect(formatTargets([{ label: 'TP', level: 1.2 }, { type: 'SL', value: 1.05 }])).toBe(
        'TP 1.2, SL 1.05',
      );
    });
    it('drops entries with no usable level/label', () => {
      expect(formatTargets([{ foo: 'bar' }, '1.10'])).toBe('1.10');
    });
  });
});
