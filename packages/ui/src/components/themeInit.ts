/**
 * The pre-paint theme script, as a plain string module.
 *
 * It must NOT live in a "use client" file. Root layouts are server
 * components; importing a non-component value from a client module gives
 * them a client reference instead of the string. The HTML still rendered the
 * script, but the RSC payload carried a lazy module reference in the root
 * layout's <head> props, so hydration had to load that chunk first. When the
 * chunk arrived after the document had parsed, the root hydrated out of step
 * with the streamed metadata outlet and React threw #418, re-rendered the root
 * from the server default (data-theme="dark"), and light-theme readers flipped
 * to dark.
 */
/** Inline in <head> before paint: <script dangerouslySetInnerHTML={{__html: themeInitScript}}/> */
export const themeInitScript =
  "try{var s=localStorage.getItem('dt-theme');var t=s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.setAttribute('data-theme',t);var c=t==='light'?'#FBFBF9':'#0A0E0C';var m=document.querySelector('meta[name=\"theme-color\"]');if(!m){m=document.createElement('meta');m.setAttribute('name','theme-color');document.head.appendChild(m)}m.setAttribute('content',c)}catch(e){document.documentElement.setAttribute('data-theme','dark')}"; // canon-allow: a <meta name="theme-color"> value is read by the browser and OS chrome, never by the page cascade, so a CSS token is unavailable here — same reason as apps/dashboard/app/manifest.ts
