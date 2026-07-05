import { useEffect, useRef } from "react";

/* ─────────────────────────────────────────────────────────────────────────
   HeroEarth — clean sphere + solar storm effects, no rings/belts
───────────────────────────────────────────────────────────────────────── */
export function HeroEarth() {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const auroraRef  = useRef<HTMLCanvasElement>(null);

  /* ── Earth sphere renderer ── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const SIZE = 290;
    canvas.width = SIZE;
    canvas.height = SIZE;
    const cx = SIZE / 2, cy = SIZE / 2, R = SIZE * 0.462;
    const DEG = 180 / Math.PI;

    const rawLX = -0.42, rawLY = -0.52, rawLZ = 0.74;
    const ll = Math.hypot(rawLX, rawLY, rawLZ);
    const LX = rawLX / ll, LY = rawLY / ll, LZ = rawLZ / ll;
    const hx = LX, hy = LY, hz = LZ + 1;
    const hl = Math.hypot(hx, hy, hz);
    const SX = hx / hl, SY = hy / hl, SZ = hz / hl;

    let raf: number;
    let rot = 0;
    let texPixels: Uint8ClampedArray | null = null;
    let TEX_W = 0, TEX_H = 0;
    let landMode: "dark" | "bright" | "alpha" = "dark";

    const terrainRGB = (lat: number, lon: number, land: boolean): [number, number, number] => {
      if (!land) return [8, 38, 90];
      if (Math.abs(lat) > 65)                              return [200, 218, 228];
      if (lat > 15 && lat < 32 && lon > -18 && lon < 42)  return [145, 118, 70];
      if (lat > 12 && lat < 30 && lon > 42  && lon < 62)  return [140, 115, 72];
      if (Math.abs(lat) > 55)                              return [80, 95, 68];
      if (lat > -18 && lat < 8 && lon > -82 && lon < -44) return [28, 78, 38];
      if (lat > -5  && lat < 8 && lon > 10  && lon < 32)  return [30, 80, 42];
      return [60, 88, 48];
    };

    const isLandTex = (lat: number, rawLon: number): boolean => {
      if (!texPixels) return false;
      const lon = ((rawLon % 360) + 540) % 360;
      const tx  = Math.floor((lon / 360) * TEX_W) % TEX_W;
      const ty  = Math.min(TEX_H - 1, Math.floor(((90 - lat) / 180) * TEX_H));
      const i   = (ty * TEX_W + tx) * 4;
      const [r, g, b, a] = [texPixels[i], texPixels[i+1], texPixels[i+2], texPixels[i+3]];
      if (landMode === "alpha")  return a > 128;
      if (landMode === "bright") return a > 200 && (r + g + b) > 550;
      return a > 200 && (r + g + b) < 350;
    };

    let frame = 0;
    const draw = () => {
      frame++;
      raf = requestAnimationFrame(draw);
      if (frame % 2 !== 0) return;

      rot += 0.0012;
      const ctx = canvas.getContext("2d")!;
      const img = ctx.createImageData(SIZE, SIZE);
      const buf = img.data;

      for (let py = 0; py < SIZE; py++) {
        for (let px = 0; px < SIZE; px++) {
          const dx = (px - cx) / R, dy = (py - cy) / R;
          const r2 = dx * dx + dy * dy;
          if (r2 >= 1) continue;

          const nz  = Math.sqrt(1 - r2);
          const lat = Math.asin(-dy) * DEG;
          const lon = (Math.atan2(dx, nz) + rot) * DEG;

          const land = isLandTex(lat, lon);
          const [tr, tg, tb] = terrainRGB(lat, lon, land);
          const diff = Math.max(0, dx * LX + dy * LY + nz * LZ);

          let spec = 0;
          if (!land && diff > 0.02) {
            const sd = Math.max(0, dx * SX + dy * SY + nz * SZ);
            spec = Math.pow(sd, 55) * 0.82;
          }

          const terminator = Math.min(1, Math.max(0, (0.07 - diff) * 15));
          const limb = Math.pow(nz, 0.52);

          let rr = (tr + diff * 50) * limb;
          let gg = (tg + diff * 56) * limb;
          let bb = (tb + diff * (land ? 38 : 92)) * limb;

          rr += spec * 168; gg += spec * 194; bb += spec * 228;

          if (terminator > 0.05) {
            const n = terminator;
            rr = land ? rr * (1 - n) + 14 * n : rr * (1 - n * 0.97);
            gg = land ? gg * (1 - n) + 10 * n : gg * (1 - n * 0.97);
            bb = land ? bb * (1 - n) +  5 * n : bb * (1 - n * 0.94);
          }

          const ae = Math.max(0, 0.26 - nz) / 0.26;
          rr += ae *  9 * diff; gg += ae * 34 * diff; bb += ae * 82 * diff;

          const idx = (py * SIZE + px) * 4;
          buf[idx]     = Math.min(255, Math.max(0, rr));
          buf[idx + 1] = Math.min(255, Math.max(0, gg));
          buf[idx + 2] = Math.min(255, Math.max(0, bb));
          buf[idx + 3] = 255;
        }
      }
      ctx.putImageData(img, 0, 0);
    };

    draw();

    const texImg = new Image();
    texImg.src = "/earth-texture.png";
    texImg.onload = () => {
      const tc = document.createElement("canvas");
      tc.width = texImg.width; tc.height = texImg.height;
      TEX_W = texImg.width; TEX_H = texImg.height;
      const tc2 = tc.getContext("2d")!;
      tc2.drawImage(texImg, 0, 0);
      texPixels = tc2.getImageData(0, 0, TEX_W, TEX_H).data;
      const samp = (lat: number, lon: number) => {
        const tx = Math.floor(((((lon % 360) + 540) % 360) / 360) * TEX_W) % TEX_W;
        const ty = Math.min(TEX_H - 1, Math.floor(((90 - lat) / 180) * TEX_H));
        const i  = (ty * TEX_W + tx) * 4;
        return { r: texPixels![i], g: texPixels![i+1], b: texPixels![i+2], a: texPixels![i+3] };
      };
      const sea = samp(0, -30); const soil = samp(20, 20);
      if (Math.abs(sea.a - soil.a) > 80) landMode = "alpha";
      else landMode = (soil.r + soil.g + soil.b) < (sea.r + sea.g + sea.b) ? "dark" : "bright";
    };

    return () => cancelAnimationFrame(raf);
  }, []);

  /* ── Aurora canvas (polar glow, animated) ── */
  useEffect(() => {
    const canvas = auroraRef.current;
    if (!canvas) return;
    const W = 300, H = 300;
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext("2d")!;
    let raf: number;
    let t = 0;

    const draw = () => {
      t += 0.015;
      ctx.clearRect(0, 0, W, H);

      // North aurora — a shifting elliptic band near top of sphere
      for (let k = 0; k < 3; k++) {
        const phase = t + k * 1.05;
        const yOff  = 28 + Math.sin(phase * 0.7) * 6;
        const xOff  = Math.sin(phase * 0.4) * 10;
        const gr = ctx.createRadialGradient(
          W / 2 + xOff, yOff, 8,
          W / 2 + xOff, yOff, 68,
        );
        const alpha = 0.12 + Math.sin(phase) * 0.06;
        gr.addColorStop(0,   `rgba(40,200,120,${alpha.toFixed(3)})`);
        gr.addColorStop(0.45,`rgba(30,170,190,${(alpha * 0.6).toFixed(3)})`);
        gr.addColorStop(1,   "rgba(0,0,0,0)");
        ctx.beginPath();
        ctx.ellipse(W / 2 + xOff, yOff, 90 + k * 10, 32 + k * 4, 0, 0, Math.PI * 2);
        ctx.fillStyle = gr;
        ctx.fill();
      }

      // South aurora
      for (let k = 0; k < 2; k++) {
        const phase = t * 0.8 + k * 1.3;
        const yOff  = H - 30 - Math.sin(phase * 0.6) * 5;
        const gr = ctx.createRadialGradient(W / 2, yOff, 6, W / 2, yOff, 55);
        const alpha = 0.09 + Math.sin(phase * 1.1) * 0.04;
        gr.addColorStop(0,   `rgba(30,160,210,${alpha.toFixed(3)})`);
        gr.addColorStop(0.5, `rgba(20,130,180,${(alpha * 0.5).toFixed(3)})`);
        gr.addColorStop(1,   "rgba(0,0,0,0)");
        ctx.beginPath();
        ctx.ellipse(W / 2, yOff, 74 + k * 8, 24 + k * 3, 0, 0, Math.PI * 2);
        ctx.fillStyle = gr;
        ctx.fill();
      }

      raf = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(raf);
  }, []);

  /* Solar storm particles — staggered config */
  const particles = Array.from({ length: 22 }, (_, i) => ({
    top:   `${4 + i * 4.4}%`,
    w:     12 + (i % 5) * 11,
    dur:   1.6 + (i % 6) * 0.38,
    delay: (i * 0.29) % 3.6,
    kind:  i % 5 === 0 ? "cme" : i % 3 === 0 ? "proton" : "wind",
  }));

  const gradients: Record<string, string> = {
    cme:    "linear-gradient(90deg,transparent,rgba(255,140,30,0.75),rgba(255,100,20,0.35),transparent)",
    proton: "linear-gradient(90deg,transparent,rgba(255,200,60,0.55),rgba(255,180,40,0.22),transparent)",
    wind:   "linear-gradient(90deg,transparent,rgba(150,195,255,0.30),rgba(130,180,255,0.10),transparent)",
  };

  return (
    <div className="relative flex items-center justify-center select-none"
      style={{ width: 420, height: 420 }}>

      {/* ── CME bow-shock halo (sun side, left) ── */}
      <div className="absolute pointer-events-none" style={{
        width: 340, height: 340,
        left: "50%", top: "50%",
        transform: "translate(-50%,-50%)",
        borderRadius: "50%",
        background: "radial-gradient(ellipse at 28% 38%, rgba(255,120,30,0.08) 0%, transparent 55%)",
        animation: "cmeHalo 4s ease-in-out infinite",
      }} />

      {/* ── Atmosphere glow ── */}
      <div className="absolute rounded-full pointer-events-none" style={{
        width: 308, height: 308,
        left: "50%", top: "50%",
        transform: "translate(-50%,-50%)",
        boxShadow: [
          "0 0 0  6px rgba(50,120,200,0.10)",
          "0 0 0 14px rgba(35, 90,175,0.06)",
          "0 0 50px     rgba(30, 80,180,0.20)",
        ].join(", "),
      }} />

      {/* ── Solar storm particle streams ── */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {particles.map((p, i) => (
          <div key={i} style={{
            position: "absolute",
            top: p.top, left: -55,
            width: p.w, height: "1px",
            background: gradients[p.kind],
            animation: `swind ${p.dur}s linear infinite`,
            animationDelay: `${p.delay}s`,
          }} />
        ))}

        {/* A few wider CME burst lines */}
        {[0, 1, 2].map((k) => (
          <div key={`cme-${k}`} style={{
            position: "absolute",
            top: `${22 + k * 28}%`,
            left: -55,
            width: 55 + k * 20,
            height: "2px",
            background: "linear-gradient(90deg,transparent,rgba(255,90,20,0.45),rgba(255,60,10,0.18),transparent)",
            animation: `swind ${2.4 + k * 0.5}s linear infinite`,
            animationDelay: `${k * 1.1}s`,
            borderRadius: "1px",
          }} />
        ))}
      </div>

      {/* ── Earth canvas ── */}
      <div className="relative rounded-full overflow-hidden" style={{
        width: 300, height: 300,
        boxShadow: [
          "inset -20px -16px 48px rgba(0,0,0,0.70)",
          "0 0 48px rgba(20,75,170,0.22)",
        ].join(", "),
        zIndex: 2,
      }}>
        <canvas ref={canvasRef} style={{ width: 300, height: 300, display: "block" }} />
        {/* Aurora overlay (on top of sphere, clipped by border-radius) */}
        <canvas
          ref={auroraRef}
          style={{
            position: "absolute", inset: 0,
            width: 300, height: 300,
            mixBlendMode: "screen",
            pointerEvents: "none",
          }}
        />
      </div>

      <style>{`
        @keyframes swind {
          from { transform: translateX(0);     opacity: 0; }
          10%  { opacity: 1; }
          78%  { opacity: 0.8; }
          to   { transform: translateX(520px); opacity: 0; }
        }
        @keyframes cmeHalo {
          0%,100% { opacity: 0.5; }
          50%      { opacity: 1.0; }
        }
      `}</style>
    </div>
  );
}
