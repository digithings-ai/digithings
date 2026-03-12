document.addEventListener('DOMContentLoaded', () => {

    // -----------------------------------------------------
    // 1. Typing Animation State specifically for the Hero
    // -----------------------------------------------------
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

    // -----------------------------------------------------
    // 2. Starfield Canvas Animation
    // -----------------------------------------------------
    const canvas = document.getElementById('network-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let width, height;
    let lastScrollY = window.scrollY;
    let scrollVelocity = 0;

    // ---- Stars ----
    const NUM_STARS = 280;
    let stars = [];

    class Star {
        constructor(randomY = true) {
            this.reset(randomY);
        }

        reset(randomY = false) {
            this.x = Math.random() * width;
            this.y = randomY ? Math.random() * height : Math.random() * height;
            // Depth layer: 0 = far (tiny, dim), 1 = close (large, bright)
            this.depth = Math.random();
            this.baseRadius = 0.3 + this.depth * 1.4;
            this.radius = this.baseRadius;
            // Twinkling
            this.twinkleSpeed = 0.005 + Math.random() * 0.015;
            this.twinklePhase = Math.random() * Math.PI * 2;
            this.baseOpacity = 0.25 + this.depth * 0.65;
            this.opacity = this.baseOpacity;
            // Parallax drift speed
            this.vy = 0.02 + this.depth * 0.06;
        }

        update(scrollDelta) {
            // Parallax scroll: farther stars move slower
            this.y -= scrollDelta * (0.05 + this.depth * 0.25);

            // Gentle autonomous drift
            this.y += this.vy * 0.1;

            // Twinkling
            this.twinklePhase += this.twinkleSpeed;
            const twinkle = Math.sin(this.twinklePhase);
            this.opacity = Math.max(0, this.baseOpacity + twinkle * 0.25 * this.depth);
            this.radius = this.baseRadius + twinkle * 0.4 * this.depth;

            // Wrap vertically
            if (this.y < -5) this.y = height + 5;
            if (this.y > height + 5) this.y = -5;
        }

        draw() {
            ctx.save();
            ctx.beginPath();
            ctx.arc(this.x, this.y, Math.max(0.3, this.radius), 0, Math.PI * 2);

            // Bright stars get a subtle glow
            if (this.depth > 0.7) {
                const grd = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.radius * 3);
                grd.addColorStop(0, `rgba(255, 255, 255, ${this.opacity})`);
                grd.addColorStop(1, `rgba(255, 255, 255, 0)`);
                ctx.fillStyle = grd;
                ctx.arc(this.x, this.y, this.radius * 3, 0, Math.PI * 2);
            } else {
                ctx.fillStyle = `rgba(255, 255, 255, ${this.opacity})`;
            }
            ctx.fill();
            ctx.restore();
        }
    }

    // ---- Shooting Stars ----
    let shootingStars = [];

    class ShootingStar {
        constructor() {
            this.reset();
        }

        reset() {
            this.x = Math.random() * width;
            this.y = Math.random() * height * 0.5;
            this.length = 80 + Math.random() * 120;
            const angle = (15 + Math.random() * 20) * (Math.PI / 180);
            const speed = 6 + Math.random() * 8;
            this.vx = Math.cos(angle) * speed;
            this.vy = Math.sin(angle) * speed;
            this.opacity = 1;
            this.fade = 0.012 + Math.random() * 0.012;
            this.alive = true;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;
            this.opacity -= this.fade;
            if (this.opacity <= 0) this.alive = false;
        }

        draw() {
            const tailX = this.x - this.vx * (this.length / 6);
            const tailY = this.y - this.vy * (this.length / 6);

            const grad = ctx.createLinearGradient(tailX, tailY, this.x, this.y);
            grad.addColorStop(0, `rgba(255, 255, 255, 0)`);
            grad.addColorStop(1, `rgba(255, 255, 255, ${this.opacity})`);

            ctx.save();
            ctx.beginPath();
            ctx.moveTo(tailX, tailY);
            ctx.lineTo(this.x, this.y);
            ctx.strokeStyle = grad;
            ctx.lineWidth = 1.5;
            ctx.stroke();
            ctx.restore();
        }
    }

    // Spawn a shooting star every ~4–9 seconds
    let shootingStarTimer = 0;
    const getNextShootingStarDelay = () => 4000 + Math.random() * 5000;
    let nextShootingStarIn = getNextShootingStarDelay();

    const initCanvas = () => {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;

        stars = [];
        for (let i = 0; i < NUM_STARS; i++) {
            stars.push(new Star(true));
        }
        shootingStars = [];
    };

    window.addEventListener('resize', initCanvas);
    initCanvas();

    // -----------------------------------------------------
    // 3. Scroll-driven reveal (throttled + batched for smooth scroll)
    // -----------------------------------------------------
    const scrollTriggers = document.querySelectorAll('.scroll-trigger');
    const heroVisual = document.querySelector('.hero-visual.scroll-trigger');
    const timelineEvents = document.querySelectorAll('.timeline-event');
    const revealThreshold = 0.85;

    let lastTime = 0;
    let frameCount = 0;

    const updateLoop = (timestamp) => {
        const dt = timestamp - lastTime;
        lastTime = timestamp;
        frameCount += 1;

        // --- A. Scroll position (every frame for star parallax) ---
        const currentScrollY = window.scrollY;
        scrollVelocity = currentScrollY - lastScrollY;
        lastScrollY = currentScrollY;

        const windowHeight = window.innerHeight;
        const activationLine = windowHeight * 0.7;
        const fullyRevealedAt = windowHeight * (1 - revealThreshold);

        // --- B. Scroll-trigger & timeline updates (every 2nd frame, batched) ---
        // Batch all layout reads first, then all DOM writes, to avoid layout thrashing.
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

        // --- C. Canvas Render ---
        ctx.clearRect(0, 0, width, height);

        // Draw stars
        for (const star of stars) {
            star.update(scrollVelocity);
            star.draw();
        }

        // Shooting stars timer & render
        shootingStarTimer += dt;
        if (shootingStarTimer >= nextShootingStarIn) {
            shootingStars.push(new ShootingStar());
            shootingStarTimer = 0;
            nextShootingStarIn = getNextShootingStarDelay();
        }

        for (let i = shootingStars.length - 1; i >= 0; i--) {
            shootingStars[i].update();
            shootingStars[i].draw();
            if (!shootingStars[i].alive) shootingStars.splice(i, 1);
        }

        scrollVelocity *= 0.8;

        requestAnimationFrame(updateLoop);
    };

    // Begin unified 60fps loop
    requestAnimationFrame(updateLoop);
});
