/**
 * Range-based syntax highlight → DocumentFragment (no innerHTML; DESLOP-027).
 * Mirrors token order in terminal/index.js naiveHighlight.
 */

/** @typedef {{ start: number; end: number; className: string }} HighlightSpan */

function overlaps(spans, start, end) {
  return spans.some((s) => start < s.end && end > s.start);
}

function pushSpan(spans, start, end, className) {
  if (start >= end || overlaps(spans, start, end)) return;
  spans.push({ start, end, className });
}

function addFullMatches(spans, text, regex, className) {
  const re = new RegExp(regex.source, regex.flags.includes('g') ? regex.flags : `${regex.flags}g`);
  let m;
  while ((m = re.exec(text)) !== null) {
    pushSpan(spans, m.index, m.index + m[0].length, className);
  }
}

/** Wrap capture group `groupIdx` (1-based). */
function addGroupMatches(spans, text, regex, className, groupIdx) {
  const re = new RegExp(regex.source, regex.flags.includes('g') ? regex.flags : `${regex.flags}g`);
  let m;
  while ((m = re.exec(text)) !== null) {
    const g = m[groupIdx];
    if (g == null) continue;
    const start = m.index + m[0].indexOf(g);
    pushSpan(spans, start, start + g.length, className);
  }
}

const KEYWORDS = {
  js: /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|throw|try|catch|finally)\b/g,
  ts: /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|interface|type|enum|public|private|readonly|throw|try|catch|finally|as)\b/g,
  tsx: /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|interface|type|throw|try|catch|finally)\b/g,
  py: /\b(def|return|if|elif|else|for|while|class|import|from|as|try|except|finally|with|lambda|async|await|True|False|None|yield|raise|not|or|and|in|is|pass|global|nonlocal)\b/g,
  sh: /\b(if|then|else|fi|for|do|done|while|case|esac|function|return|export|echo|cd|source)\b/g,
  json: /\b(true|false|null)\b/g,
};

const BUILTINS = {
  py: /\b(str|int|float|bool|bytes|dict|list|tuple|set|frozenset|Any|Optional|Union|Callable|Type|None|Self|object|range|len|print|isinstance|issubclass|enumerate|zip|map|filter)\b/g,
  ts: /\b(string|number|boolean|void|never|any|unknown|Promise|Record|Partial|Readonly|Pick|Omit|Array|Map|Set|Date|Request|Response|JSON|Math)\b/g,
  tsx: /\b(string|number|boolean|void|any|unknown|Promise|Record|Partial|Readonly)\b/g,
  js: null,
  sh: null,
  json: null,
};

export function collectHighlightSpans(text, lang) {
  /** @type {HighlightSpan[]} */
  const spans = [];

  addFullMatches(spans, text, /(["'`])((?:\\.|(?!\1).)*)\1/g, 'term-tok-str');

  if (lang === 'py' || lang === 'sh') {
    addGroupMatches(spans, text, /(^|[^#])(#[^\n]*)/g, 'term-tok-cmt', 2);
  } else if (lang !== 'json') {
    addGroupMatches(spans, text, /(^|[^:])((?:\/\/)[^\n]*)/g, 'term-tok-cmt', 2);
  }

  if (lang === 'py') {
    addGroupMatches(spans, text, /(^|\s)(@\w[\w.]*)/g, 'term-tok-dec', 2);
  }

  addFullMatches(spans, text, /\b(\d+(?:\.\d+)?)\b/g, 'term-tok-num');

  const kw = KEYWORDS[lang];
  if (kw) addFullMatches(spans, text, kw, 'term-tok-kw');

  const bi = BUILTINS[lang];
  if (bi) addFullMatches(spans, text, bi, 'term-tok-type');

  if (lang === 'py' || lang === 'ts' || lang === 'tsx') {
    addFullMatches(spans, text, /(->|\|)/g, 'term-tok-op');
  }

  spans.sort((a, b) => a.start - b.start || b.end - a.end);
  return spans;
}

export function buildHighlightFragment(text, lang) {
  const spans = collectHighlightSpans(text, lang);
  const frag = document.createDocumentFragment();
  let pos = 0;
  for (const { start, end, className } of spans) {
    if (start < pos) continue;
    if (pos < start) frag.appendChild(document.createTextNode(text.slice(pos, start)));
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text.slice(start, end);
    frag.appendChild(span);
    pos = end;
  }
  if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
  return frag;
}

export function mountHighlighted(el, text, lang) {
  el.replaceChildren();
  if (!text) return;
  el.append(buildHighlightFragment(text, lang));
}
