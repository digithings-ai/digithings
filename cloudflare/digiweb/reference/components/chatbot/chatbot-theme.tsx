"use client";

/**
 * Local theme toggle for the isolated /chatbot root.
 * Same `dt-theme` key as @digithings/web ThemeProvider — do not import the
 * web barrel from this tree (it pulls the whole package into webpack).
 */
const KEY = "dt-theme";
const THEME_BG = { light: "#FBFBF9", dark: "#0A0E0C" } as const;

export const chatbotThemeInitScript =
  "try{var s=localStorage.getItem('dt-theme');var t=s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.setAttribute('data-theme',t);var c=t==='light'?'#FBFBF9':'#0A0E0C';var m=document.querySelector('meta[name=\"theme-color\"]');if(!m){m=document.createElement('meta');m.setAttribute('name','theme-color');document.head.appendChild(m)}m.setAttribute('content',c)}catch(e){document.documentElement.setAttribute('data-theme','dark')}";

function applyThemeColor(theme: "light" | "dark") {
  try {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", THEME_BG[theme]);
  } catch {
    /* ignore */
  }
}

export function ChatbotThemeToggle() {
  return (
    <button
      type="button"
      className="chatbot-theme-toggle"
      aria-label="Toggle colour theme"
      title="Toggle theme"
      onClick={() => {
        const current =
          document.documentElement.getAttribute("data-theme") === "light"
            ? "light"
            : "dark";
        const next = current === "light" ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", next);
        applyThemeColor(next);
        try {
          localStorage.setItem(KEY, next);
        } catch {
          /* ignore */
        }
      }}
    >
      theme
    </button>
  );
}
