import { vi } from "vitest";
const pin = process.env.PROBE_CLOCK;
if (pin) { vi.useFakeTimers(); vi.setSystemTime(new Date(pin)); }
