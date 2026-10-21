# Review assets for digithings PR #6110

Visual evidence for the base-skin countdown surface review (DIG-4799), at head
`01a1e3adbbe375cea744eecc8f6677eecaa8618a`.

Each shot renders the real component from `packages/ui` (base skin thread and the
gallery thread) in a Vite harness with the repository theme CSS, so the pixels
come from the shipped code, not from a mock-up.

| file | what it shows |
| --- | --- |
| `base-countdown-light.png` | base skin, text already streamed, connection part in `warming_up` state, light theme |
| `base-countdown-dark.png` | the same row in the dark theme |
| `base-countdown-cleared.png` | the same turn after the adapter writes `state: "ready"`: the countdown row is gone and the pulsing working dot is back |
| `gallery-countdown.png` | the gallery skin with the same parts: the answer text and nothing else, no countdown row, no working dot |

The message under test is the adapter's own string:
`Hit the model's per-minute token limit — resuming in 25s (retry 1 of 3)`.
