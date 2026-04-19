document.addEventListener('DOMContentLoaded', () => {
    let typeWriterStarted = false;
    const terminalCode = `from digithings import digigraph\n\n# Initialize orchestrator\nagent = digigraph(mode="secure")\n\n# Connect execution engine\nagent.attach("nautilus_core")\n\nagent.run()`;

    const typeWriter = (text, i, fnCallback) => {
        if (i < (text.length)) {
            document.getElementById("typewriter-code").innerHTML = text.substring(0, i+1) +'<span aria-hidden="true"></span>';
            setTimeout(() => {
                typeWriter(text, i + 1, fnCallback)
            }, 30);
        } else if (typeof fnCallback == 'function') {
            setTimeout(fnCallback, 700);
        }
    };

    const canvas = document.getElementById('network-canvas');
    if (!canvas) return;
    // Feature-detect 2D canvas. If unsupported, #bg-base solid color shows through.
    const ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) {
        canvas.style.display = 'none';
        return;
    }

    let width, height;

    // Reduce star count on small viewports to keep mobile frame-rate >= 30fps.
    const mobileQuery = window.matchMedia && window.matchMedia('(max-width: 480px)');
    const isMobile = !!(mobileQuery && mobileQuery.matches);
    const N = isMobile ? 80 : 180;
    const stars = Array.from({ length: N }, () => ({
        x: Math.random(),
        y: Math.random(),
        d: Math.random(),
        ph: Math.random() * Math.PI * 2,
    }));

    const initCanvas = () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', initCanvas);
    initCanvas();

    const scrollTriggers = document.querySelectorAll('.scroll-trigger');
    const heroVisual = document.querySelector('.hero-visual.scroll-trigger');
    const timelineEvents = document.querySelectorAll('.timeline-event');
    const revealThreshold = 0.85;

    let frameCount = 0;
    let rafId = null;

    const updateLoop = () => {
        frameCount += 1;

        const windowHeight = window.innerHeight;
        const activationLine = windowHeight * 0.7;
        const fullyRevealedAt = windowHeight * (1 - revealThreshold);

        if (frameCount % 2 === 0) {
            const triggerData = [];
            for (let i = 0; i < scrollTriggers.length; i++) {
                triggerData.push({ el: scrollTriggers[i], rect: scrollTriggers[i].getBoundingClientRect() });
            }
            const timelineData = [];
            for (let i = 0; i < timelineEvents.length; i++) {
                timelineData.push({ el: timelineEvents[i], rect: timelineEvents[i].getBoundingClientRect() });
            }

            for (const { el, rect } of triggerData) {
                const distanceFromBottom = windowHeight - rect.top;
                let progress = 0;
                if (distanceFromBottom > 0) {
                    progress = Math.min(1, Math.max(0, distanceFromBottom / fullyRevealedAt));
                }
                if (rect.top <= 0) progress = 1;
                el.style.setProperty('--scroll', progress);

                if (el === heroVisual && progress > 0.5 && !typeWriterStarted) {
                    typeWriterStarted = true;
                    setTimeout(() => {
                        typeWriter(terminalCode, 0, () => {});
                    }, 400);
                }
            }

            for (const { el, rect } of timelineData) {
                if (rect.top < activationLine) {
                    el.classList.add('active');
                } else {
                    el.classList.remove('active');
                }
            }
        }

        ctx.clearRect(0, 0, width, height);

        for (const s of stars) {
            s.ph += 0.01 + s.d * 0.015;
            const tw = 0.6 + 0.4 * Math.sin(s.ph);
            const r = 0.35 + s.d * 1.1;
            const o = 0.2 + s.d * 0.55 * tw;
            ctx.beginPath();
            ctx.fillStyle = `rgba(230,230,230,${o})`;
            ctx.arc(s.x * width, s.y * height, r, 0, Math.PI * 2);
            ctx.fill();
            s.y -= 0.00015 + s.d * 0.0002;
            if (s.y < 0) s.y = 1;
        }

        rafId = requestAnimationFrame(updateLoop);
    };

    // Pause the animation loop when the tab is hidden; resume when visible.
    // Drops idle-tab CPU to zero.
    const start = () => {
        if (rafId === null) {
            rafId = requestAnimationFrame(updateLoop);
        }
    };
    const stop = () => {
        if (rafId !== null) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
    };
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stop();
        } else {
            start();
        }
    });

    start();
});
