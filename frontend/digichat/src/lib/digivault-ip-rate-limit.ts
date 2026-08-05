import { checkBffRateLimit, envPositiveInt } from "@/lib/bff-rate-limit";

export const DIGIVAULT_IP_RATE_LIMIT_MAX = envPositiveInt(
  "DIGICHAT_DIGIVAULT_IP_RATE_LIMIT_MAX",
  60
);
const WINDOW_MS = envPositiveInt("DIGICHAT_DIGIVAULT_IP_RATE_LIMIT_WINDOW_MS", 60_000);

export function checkDigivaultIpRateLimit(ip: string) {
  return checkBffRateLimit(`digivault-ip:${ip}`, DIGIVAULT_IP_RATE_LIMIT_MAX, WINDOW_MS);
}

export const DIGIVAULT_RATE_LIMIT_MESSAGE = "rate limit exceeded — slow down a moment";
