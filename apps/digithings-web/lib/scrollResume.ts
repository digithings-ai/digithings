/**
 * Reload / back-forward restore, without the intro replaying.
 *
 * `HashScrollManager` (kit) puts the reader back where they were, but only after
 * hydration, so the first paint is the top of the page: the hero wordmark builds,
 * then the page jumps. Two tiny inline scripts close that gap. The head one reads
 * the position `HashScrollManager` saves in sessionStorage and, when the visit is
 * a reload/back-forward below `SCROLL_RESUME_MIN_Y`, flags `html.scroll-resumed`
 * (globals.css turns the hero intro off for it). The body-end one scrolls there
 * before first paint. A cold visit, or one at the top, is untouched and keeps the
 * full intro. `HashScrollManager` still refines the position once the page has
 * settled; this only makes the first frame the right one.
 */
export const SCROLL_RESUME_MIN_Y = 40;

export const SCROLL_RESUME_FLAG =
  "try{var n=performance.getEntriesByType('navigation')[0],t=n&&n.type;" +
  "if(t==='reload'||t==='back_forward'){" +
  "var r=sessionStorage.getItem('dg-scroll:'+location.pathname+location.search)," +
  "y=r&&JSON.parse(r).y;" +
  `if(typeof y==='number'&&y>${SCROLL_RESUME_MIN_Y}){` +
  "document.documentElement.classList.add('scroll-resumed');window.__dtResumeY=y}}}catch(e){}";

export const SCROLL_RESUME_PLACE =
  "try{var y=window.__dtResumeY;if(y){history.scrollRestoration='manual';" +
  "window.scrollTo({top:y,behavior:'instant'})}}catch(e){}";
