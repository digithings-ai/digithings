import { describe, expect, it } from 'vitest';
import { nextChannelTopic } from './use-live-prices';

/**
 * The channel topic is the whole of #1833's realtime-lane fix, and every way of getting it
 * wrong fails SILENTLY — no exception, no console error, no subscribe-status callback, just
 * quotes that stop arriving while the table keeps rendering the last one it saw. So the
 * uniqueness contract is pinned here rather than left to the reader of the comment.
 *
 * `RealtimeClient.channel(topic)` DEDUPES BY TOPIC: handed a topic it already holds, it returns
 * the existing channel. `removeChannel()` does not remove synchronously — phoenix puts the
 * channel in `leaving` and the client's `_remove` runs only from its `_onClose` — so a channel
 * being torn down is still in `client.channels` when the next subscription is created.
 */
describe('nextChannelTopic — no two subscriptions may share a topic (#1833)', () => {
  it('gives the SAME hook instance a different topic every time', () => {
    // The reachable case: one mounted consumer whose effect re-runs (the positions↔activity
    // toggle, or leaving and returning to the holdings tab). `useId` is constant across those,
    // so this is the only thing standing between a remount and a dead realtime lane.
    const first = nextChannelTopic('_R_1_');
    const second = nextChannelTopic('_R_1_');
    expect(second).not.toBe(first);
  });

  it('keeps two mounted consumers apart as well', () => {
    expect(nextChannelTopic('_R_1_')).not.toBe(nextChannelTopic('_R_2_'));
  });

  it('never repeats a topic across a long run of subscriptions', () => {
    const topics = Array.from({ length: 200 }, () => nextChannelTopic('_R_1_'));
    expect(new Set(topics).size).toBe(topics.length);
  });

  it('still carries the prefix and the instance id, and stays phoenix-safe', () => {
    const topic = nextChannelTopic('_R_7_');
    expect(topic.startsWith('dashboard-prices-live-_R_7_-')).toBe(true);
    // Sent verbatim in the phoenix join, so the whole topic stays in the safe character set
    // the instance id is already stripped down to.
    expect(topic).toMatch(/^[A-Za-z0-9_-]+$/);
  });
});
