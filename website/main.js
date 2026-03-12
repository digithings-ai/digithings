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
    // 2. Interactive Canvas "Web of Dots"
    // -----------------------------------------------------
    const canvas = document.getElementById('network-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    let width, height;
    let nodes = [];
    const maxNodes = 60; // Keep lower for performance
    const connectionRadius = 160;
    
    let lastScrollY = window.scrollY;
    let scrollVelocity = 0;
    
    // Track mouse position for subtle interactivity
    let mouse = { x: -1000, y: -1000 };
    document.addEventListener('mousemove', (e) => {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
    });
    
    class Node {
        constructor() {
            this.x = Math.random() * window.innerWidth;
            this.y = Math.random() * window.innerHeight;
            this.vx = (Math.random() - 0.5) * 0.4;
            this.vy = (Math.random() - 0.5) * 0.4;
            this.radius = Math.random() * 2 + 0.5;
        }
        
        update() {
            // Apply scroll velocity (parallax magic)
            this.y -= scrollVelocity * 0.4; // Moves opposite to user scroll
            
            // Apply normal autonomous drift
            this.x += this.vx;
            this.y += this.vy;
            
            // Mouse interaction: repel slightly from cursor
            const dx = mouse.x - this.x;
            const dy = mouse.y - this.y;
            const dist = Math.sqrt(dx*dx + dy*dy);
            if (dist < 120) {
                this.x -= dx * 0.02;
                this.y -= dy * 0.02;
            }
            
            // Wrap to opposite side of screen if flowing off bounds
            if (this.x < 0) this.x = width;
            if (this.x > width) this.x = 0;
            if (this.y < -50) this.y = height + 50; 
            if (this.y > height + 50) this.y = -50;
        }
        
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
            ctx.fill();
        }
    }
    
    const initCanvas = () => {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = width;
        canvas.height = height;
        
        nodes = [];
        for (let i = 0; i < maxNodes; i++) {
            nodes.push(new Node());
        }
    };
    
    window.addEventListener('resize', initCanvas);
    initCanvas();

    // -----------------------------------------------------
    // 3. Apple-Style Scroll Interpolator & Unified Game Loop
    // -----------------------------------------------------
    const scrollTriggers = document.querySelectorAll('.scroll-trigger');
    const heroVisual = document.querySelector('.hero-visual.scroll-trigger');
    const revealThreshold = 0.85; 
    
    const updateLoop = () => {
        // --- A. Scroll Math ---
        const currentScrollY = window.scrollY;
        scrollVelocity = currentScrollY - lastScrollY;
        lastScrollY = currentScrollY;
        
        const windowHeight = window.innerHeight;
        
        scrollTriggers.forEach((el) => {
            const rect = el.getBoundingClientRect();
            const distanceFromBottom = windowHeight - rect.top;
            const fullyRevealedAt = windowHeight * (1 - revealThreshold);
            
            let progress = 0;
            if (distanceFromBottom > 0) {
                progress = Math.min(1, Math.max(0, distanceFromBottom / fullyRevealedAt));
            }
            if (rect.top <= 0) progress = 1;

            // Drive CSS Opacity & Transforms
            el.style.setProperty('--scroll', progress);
            
            // Turn on typewriter once the terminal hits viewport bounds
            if (el === heroVisual && progress > 0.5 && !typeWriterStarted) {
                typeWriterStarted = true;
                setTimeout(() => {
                    typeWriter(terminalCode, 0, () => {});
                }, 400);
            }
        });

        // Handle timeline event activation — once scrolled past top 70% of viewport, stay active
        const timelineEvents = document.querySelectorAll('.timeline-event');
        const activationLine = window.innerHeight * 0.7;

        timelineEvents.forEach(event => {
            const rect = event.getBoundingClientRect();
            if (rect.top < activationLine) {
                event.classList.add('active');
            } else {
                event.classList.remove('active');
            }
        });
        
        // --- B. Canvas Render Math ---
        ctx.clearRect(0, 0, width, height);
        
        for (let i = 0; i < nodes.length; i++) {
            nodes[i].update();
            nodes[i].draw();
            
            // N-squared distance check to draw connecting neural web lines
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x;
                const dy = nodes[i].y - nodes[j].y;
                const dist = Math.sqrt(dx*dx + dy*dy);
                
                if (dist < connectionRadius) {
                    ctx.beginPath();
                    ctx.moveTo(nodes[i].x, nodes[i].y);
                    ctx.lineTo(nodes[j].x, nodes[j].y);
                    // Proximity fading
                    const opacity = 1 - (dist / connectionRadius);
                    ctx.strokeStyle = `rgba(180, 180, 180, ${opacity * 0.12})`;
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }
        }
        
        scrollVelocity *= 0.8; // Decay velocity back to rest when not scrolling
        
        requestAnimationFrame(updateLoop);
    };

    // Begin unified 60fps loop
    requestAnimationFrame(updateLoop);
});
