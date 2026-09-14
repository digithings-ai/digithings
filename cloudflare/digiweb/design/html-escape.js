/** Escape text for safe inclusion in integrator HTML slots (SIMP-030 / DESLOP-027). */
export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));
}

/** Mount escapeHtml()-safe markup from trusted template literals (DESLOP-027). */
export function mountTrustedHtml(el, html) {
  el.replaceChildren();
  if (!html) return;
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  el.append(tpl.content);
}
