import { useEffect, useRef } from "react";

interface Star {
  x: number;
  y: number;
  d: number;
  ph: number;
}

export function StarField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = 0;
    let h = 0;
    const N = 180;
    const stars: Star[] = Array.from({ length: N }, () => ({
      x: Math.random(),
      y: Math.random(),
      d: Math.random(),
      ph: Math.random() * Math.PI * 2,
    }));

    function resize() {
      if (!canvas) return;
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    }

    resize();
    window.addEventListener("resize", resize);

    let rafId: number;
    function frame() {
      if (!ctx) return;
      ctx.fillStyle = "#000000";
      ctx.fillRect(0, 0, w, h);
      for (const s of stars) {
        s.ph += 0.01 + s.d * 0.015;
        const tw = 0.6 + 0.4 * Math.sin(s.ph);
        const r = 0.35 + s.d * 1.1;
        const o = 0.2 + s.d * 0.55 * tw;
        ctx.beginPath();
        ctx.fillStyle = `rgba(230,230,230,${o})`;
        ctx.arc(s.x * w, s.y * h, r, 0, Math.PI * 2);
        ctx.fill();
        s.y -= 0.00015 + s.d * 0.0002;
        if (s.y < 0) s.y = 1;
      }
      rafId = requestAnimationFrame(frame);
    }
    frame();

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 -z-10 pointer-events-none"
      aria-hidden="true"
    />
  );
}
