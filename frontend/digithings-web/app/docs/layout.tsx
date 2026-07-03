import type { ReactNode } from "react";

// /docs defaults to the ivory reading mode (canon §14: long-form surfaces go
// light). An explicit user choice (dt-theme in localStorage) still wins and
// the ThemeToggle keeps working — this only changes the *default* for this
// route. Inline script so it runs during parse, before this segment paints
// (the root themeInitScript in <head> has already run; re-setting the
// attribute here is still pre-paint, so there is no flash).
const docsIvoryInit =
  "try{if(!localStorage.getItem('dt-theme')){document.documentElement.setAttribute('data-theme','light');var m=document.querySelector('meta[name=\"theme-color\"]');if(m)m.setAttribute('content','#FBFBF9')}}catch(e){}";

export default function DocsSegmentLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: docsIvoryInit }} />
      {children}
    </>
  );
}
