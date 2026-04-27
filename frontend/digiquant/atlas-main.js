/**
 * atlas.html — page entry module.
 *
 * Lightweight compared to digiquant main.js:
 *   - Hero equity-curve draw-in animation
 *   - Counter animations for metric cards
 *   - No ticker, no living-architecture diagram
 */

// --- Counter animation (shared with digiquant main.js) -------------------
function formatCount(value, decimals, suffix) {
    const n = decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
    return suffix ? `${n}${suffix}` : n;
}

function animateCounter(el) {
    if (el.dataset.countDone === '1') return;
    el.dataset.countDone = '1';
    const target = parseFloat(el.dataset.countTo);
    const decimals = parseInt(el.dataset.countDecimals || '0', 10);
    const suffix = el.dataset.countSuffix || '';
    if (!Number.isFinite(target)) return;

    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReduced) {
        el.textContent = formatCount(target, decimals, suffix);
        return;
    }

    const duration = 900;
    const start = performance.now();
    let finalized = false;

    function step(now) {
        if (finalized) return;
        const t = Math.min(1, (now - start) / duration);
        const k = 1 - Math.pow(1 - t, 3);
        el.textContent = formatCount(target * k, decimals, suffix);
        if (t < 1) {
            requestAnimationFrame(step);
        } else {
            finalized = true;
            el.textContent = formatCount(target, decimals, suffix);
        }
    }
    requestAnimationFrame(step);
    setTimeout(() => {
        if (finalized) return;
        finalized = true;
        el.textContent = formatCount(target, decimals, suffix);
    }, duration + 200);
}

function initCounters() {
    const counters = document.querySelectorAll('[data-count-to]');
    if (counters.length === 0) return;
    if (!('IntersectionObserver' in window)) {
        counters.forEach(animateCounter);
        return;
    }
    const io = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                animateCounter(entry.target);
                io.unobserve(entry.target);
            }
        }
    }, { threshold: [0, 0.15], rootMargin: '0px 0px -8% 0px' });
    counters.forEach((el) => io.observe(el));
}

// --- Hero curve draw-in --------------------------------------------------
function initDrawIn() {
    const path = document.querySelector('.atl-draw-in');
    if (!path) return;
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const length = path.getTotalLength ? path.getTotalLength() : 2200;
    path.style.strokeDasharray = String(length);
    if (prefersReduced) {
        path.style.strokeDashoffset = '0';
        return;
    }
    path.style.strokeDashoffset = String(length);
    requestAnimationFrame(() => {
        path.style.transition = 'stroke-dashoffset 2200ms cubic-bezier(0.2, 0.8, 0.2, 1)';
        path.style.strokeDashoffset = '0';
    });
    setTimeout(() => {
        if (path.style.strokeDashoffset !== '0') {
            path.style.strokeDashoffset = '0';
        }
    }, 2400);
}

// --- Boot ----------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    initDrawIn();
    initCounters();
});
