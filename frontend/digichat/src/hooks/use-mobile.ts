import { useSyncExternalStore } from "react"

const MOBILE_BREAKPOINT = 768
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

// Lazily cached so module load in SSR/test environments doesn't touch window
let mql: MediaQueryList | null = null
function getMql(): MediaQueryList {
  if (!mql) mql = window.matchMedia(MOBILE_QUERY)
  return mql
}

function subscribe(callback: () => void) {
  const m = getMql()
  m.addEventListener("change", callback)
  return () => m.removeEventListener("change", callback)
}

function getSnapshot() {
  return getMql().matches
}

function getServerSnapshot() {
  return false // SSR: window is unavailable, default to non-mobile
}

export function useIsMobile() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
