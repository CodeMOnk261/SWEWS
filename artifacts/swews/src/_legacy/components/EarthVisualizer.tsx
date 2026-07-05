import { useEffect, useRef, useState } from "react";
import { Zap, Shield, Activity, RefreshCw, Compass } from "lucide-react";
import { API_BASE, WS_BASE } from "@/lib/api";

interface SpaceWeatherPhysicsData {
  intensity: number;
  state: string;
  scaling_factor: number;
  wind_speed: number;
  density: number;
  bz: number;
  dynamic_pressure: number;
  timestamp: number;
  live: boolean;
}

interface Particle {
  x: number;
  y: number;
  speed: number;
  size: number;
  opacity: number;
  angleOffset: number;
  deflected: boolean;
}

export function EarthVisualizer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Real-time telemetry states
  const [data, setData] = useState<SpaceWeatherPhysicsData>({
    intensity: 0.15,
    state: "Calm Conditions",
    scaling_factor: 0.9,
    wind_speed: 400.0,
    density: 5.0,
    bz: 1.5,
    dynamic_pressure: 1.6,
    timestamp: Date.now(),
    live: false
  });

  const [isLive, setIsLive] = useState(false);
  const [useManual, setUseManual] = useState(false);
  const [manualIntensity, setManualIntensity] = useState(0.15);

  // Reference for WebGL/Canvas update loop
  const physicsRef = useRef<SpaceWeatherPhysicsData>({
    intensity: 0.15,
    state: "Calm Conditions",
    scaling_factor: 0.9,
    wind_speed: 400.0,
    density: 5.0,
    bz: 1.5,
    dynamic_pressure: 1.6,
    timestamp: Date.now(),
    live: false
  });

  // Synchronize React states to loop references
  useEffect(() => {
    if (useManual) {
      const v = 400.0 + 400.0 * manualIntensity; // 400 to 800 km/s
      const n = 4.0 + 20.0 * manualIntensity;     // 4 to 24 N/cm3
      const bz = 2.0 - 20.0 * manualIntensity;     // +2 to -18 nT
      const p_dyn = 1.67e-6 * n * (v ** 2);
      const scaling = Math.max(0.38, Math.min(1.2, (p_dyn / 2.0) ** (-1.0/6.0)));

      const manualState = manualIntensity < 0.35 
        ? "Calm Conditions" 
        : manualIntensity < 0.7 
          ? "X3 Solar Flare" 
          : "Carrington Event";

      const manualPayload = {
        intensity: manualIntensity,
        state: manualState,
        scaling_factor: scaling,
        wind_speed: v,
        density: n,
        bz: bz,
        dynamic_pressure: p_dyn,
        timestamp: Date.now(),
        live: false
      };

      physicsRef.current = manualPayload;
      setData(manualPayload);
    } else {
      physicsRef.current = data;
    }
  }, [data, manualIntensity, useManual]);

  // Establish connection to live FastAPI Server (WebSocket + Polling fallback)
  useEffect(() => {
    if (useManual) return;

    let socket: WebSocket | null = null;
    let pollInterval: NodeJS.Timeout | null = null;
    let mockInterval: NodeJS.Timeout | null = null;

    const connectWebSocket = () => {
      try {
        socket = new WebSocket(`${WS_BASE}/ws/intensity`);

        socket.onopen = () => {
          console.log("SWEWS 2D Canvas: WebSocket connected.");
          setIsLive(true);
          if (pollInterval) clearInterval(pollInterval);
          if (mockInterval) clearInterval(mockInterval);
        };

        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            setData(payload);
          } catch (err) {
            console.error("SWEWS 2D Canvas: Error parsing WS packet:", err);
          }
        };

        socket.onerror = () => {
          socket?.close();
        };

        socket.onclose = () => {
          setIsLive(false);
          startHTTPPolling();
        };
      } catch (e) {
        startHTTPPolling();
      }
    };

    const startHTTPPolling = () => {
      if (pollInterval) clearInterval(pollInterval);

      pollInterval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/regression-intensity`);
          if (res.ok) {
            const payload = await res.json();
            setData(payload);
            setIsLive(true);

            if (!socket || socket.readyState === WebSocket.CLOSED) {
              connectWebSocket();
            }
          } else {
            throw new Error("HTTP failure");
          }
        } catch {
          setIsLive(false);
          startMockSimulator();
        }
      }, 1200);
    };

    const startMockSimulator = () => {
      if (mockInterval) return;

      console.log("SWEWS 2D Canvas: API offline, cycling mock environment.");
      mockInterval = setInterval(() => {
        const cycle = 50000; // 50s cycle
        const elapsed = Date.now() % cycle;
        const ratio = elapsed / cycle;

        let intensity = 0.15;
        let state = "Calm Conditions";

        if (ratio < 0.35) {
          intensity = 0.12 + 0.08 * Math.sin(ratio * Math.PI * 3.0);
          state = "Calm Conditions";
        } else if (ratio < 0.7) {
          intensity = 0.46 + 0.14 * Math.sin((ratio - 0.35) * Math.PI * 3.0);
          state = "X3 Solar Flare";
        } else {
          intensity = 0.85 + 0.12 * Math.sin((ratio - 0.7) * Math.PI * 3.0);
          state = "Carrington Event";
        }

        const v = 400.0 + 420.0 * intensity;
        const n = 5.0 + 18.0 * intensity;
        const bz = 2.0 - 20.0 * intensity;
        const p_dyn = 1.67e-6 * n * (v ** 2);
        const scaling = Math.max(0.38, Math.min(1.2, (p_dyn / 2.0) ** (-1.0/6.0)));

        setData({
          intensity,
          state,
          scaling_factor: scaling,
          wind_speed: v,
          density: n,
          bz,
          dynamic_pressure: p_dyn,
          timestamp: Date.now(),
          live: false
        });
      }, 350);
    };

    connectWebSocket();

    return () => {
      socket?.close();
      if (pollInterval) clearInterval(pollInterval);
      if (mockInterval) clearInterval(mockInterval);
    };
  }, [useManual]);

  // 2D High-Performance Rendering Logic
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let animationFrameId: number;

    const resizeCanvas = () => {
      const container = containerRef.current;
      if (!container) return;
      width = container.clientWidth;
      height = container.clientHeight;
      canvas.width = width * window.devicePixelRatio;
      canvas.height = height * window.devicePixelRatio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    // Initialize Solar Wind particles
    const particleCount = 45;
    const particles: Particle[] = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        speed: 1.5 + Math.random() * 2,
        size: 1.0 + Math.random() * 1.5,
        opacity: 0.25 + Math.random() * 0.5,
        angleOffset: (Math.random() * 0.2 - 0.1),
        deflected: false
      });
    }

    // Magnetic field parameters
    const DIPOLE_MOMENT = 60000; // Scaled dipole moment strength
    const DIPOLE_TILT = (11.5 * Math.PI) / 180; // Earth's magnetic tilt

    // Cache for magnetic field lines to avoid recalculating every frame when parameters haven't changed
    const fieldLinesCache = useRef<{ x: number; y: number }[][] | null>(null);
    const lastParams = useRef({ bExtX: 0, bExtY: 0, R_earth: 0 });

    const traceFieldLine = (
      x0: number,
      y0: number,
      dir: number,
      bExtX: number,
      bExtY: number,
      rEarth: number
    ) => {
      const pts: { x: number; y: number }[] = [];
      let px = x0;
      let py = y0;
      const step = 2.0;
      const maxSteps = 160;

      const ux = Math.sin(DIPOLE_TILT);
      const uy = Math.cos(DIPOLE_TILT);

      for (let i = 0; i < maxSteps; i++) {
        const r = Math.hypot(px, py);
        if (r < rEarth * 0.95) break; // Entered Earth
        if (r > rEarth * 30.0) break; // Escaped tail boundary

        const r2 = r * r;
        const r5 = r2 * r2 * r;
        const dot = px * ux + py * uy;

        // 2D Dipole field formula
        const Bx_dip = (3.0 * dot * px - r2 * ux) * DIPOLE_MOMENT / r5;
        const By_dip = (3.0 * dot * py - r2 * uy) * DIPOLE_MOMENT / r5;

        // Superposed with uniform compressed external IMF sheath field
        const Bx = Bx_dip + bExtX;
        const By = By_dip + bExtY;

        const B_len = Math.hypot(Bx, By);
        if (B_len < 1e-6) break;

        px += (Bx / B_len) * step * dir;
        py += (By / B_len) * step * dir;
        pts.push({ x: px, y: py });
      }
      return pts;
    };

    const render = () => {
      const p = physicsRef.current;
      const intensity = p.intensity;
      const scaling = p.scaling_factor;
      const speed = p.wind_speed;
      const bz = p.bz;

      ctx.clearRect(0, 0, width, height);

      // Define coordinates relative to Earth center
      const cx = width * 0.28;
      const cy = height * 0.5;
      const R_earth = Math.min(width, height) * 0.075;

      // Magnetospheric physical parameters scaled to canvas dimensions
      const R_shock = R_earth * 5.4 * scaling; // Bow shock standoff distance
      const curvature = 0.0016 / (scaling * 0.9);

      // 1. Render Background Gradients (Dayside Sheath vs. Nightside Tail)
      const gradBg = ctx.createLinearGradient(0, 0, width, 0);
      if (intensity < 0.35) {
        gradBg.addColorStop(0, "#030612");
        gradBg.addColorStop(1, "#05070a");
      } else if (intensity < 0.7) {
        gradBg.addColorStop(0, "#120e03");
        gradBg.addColorStop(1, "#05070a");
      } else {
        gradBg.addColorStop(0, "#1c0707");
        gradBg.addColorStop(1, "#05070a");
      }
      ctx.fillStyle = gradBg;
      ctx.fillRect(0, 0, width, height);

      // 2. Draw Solar Wind Sheath Layer (Gradient on the left of Bow Shock)
      ctx.beginPath();
      ctx.moveTo(0, 0);
      for (let y = 0; y <= height; y += 10) {
        const x = cx - R_shock - curvature * Math.pow(y - cy, 2);
        ctx.lineTo(x, y);
      }
      ctx.lineTo(0, height);
      ctx.closePath();

      const gradSheath = ctx.createLinearGradient(cx - R_shock, cy, 0, cy);
      if (intensity < 0.35) {
        gradSheath.addColorStop(0, "rgba(14, 165, 233, 0.18)");
        gradSheath.addColorStop(1, "rgba(14, 165, 233, 0.0)");
      } else if (intensity < 0.7) {
        gradSheath.addColorStop(0, "rgba(245, 158, 11, 0.24)");
        gradSheath.addColorStop(1, "rgba(245, 158, 11, 0.02)");
      } else {
        gradSheath.addColorStop(0, "rgba(239, 68, 68, 0.42)");
        gradSheath.addColorStop(1, "rgba(239, 68, 68, 0.05)");
      }
      ctx.fillStyle = gradSheath;
      ctx.fill();

      // 3. Draw Magnetotail Plasma Sheet Glow
      const gradTail = ctx.createLinearGradient(cx, cy, width, cy);
      if (intensity < 0.35) {
        gradTail.addColorStop(0, "rgba(14, 165, 233, 0.12)");
        gradTail.addColorStop(1, "rgba(14, 165, 233, 0)");
      } else if (intensity < 0.7) {
        gradTail.addColorStop(0, "rgba(245, 158, 11, 0.15)");
        gradTail.addColorStop(1, "rgba(245, 158, 11, 0)");
      } else {
        gradTail.addColorStop(0, "rgba(239, 68, 68, 0.22)");
        gradTail.addColorStop(1, "rgba(239, 68, 68, 0)");
      }
      ctx.fillStyle = gradTail;
      ctx.fillRect(cx, cy - 25, width - cx, 50);

      // 4. Update and render magnetic field lines (cached)
// Update field lines cache if parameters have changed
      const bExtX = 14.0 * (1.0 / scaling); // Sunward compression field
      const bExtY = -bz * 2.8;             // Southward IMF Bz reconnection field

      if (
         bExtX !== lastParams.current.bExtX ||
         bExtY !== lastParams.current.bExtY ||
         R_earth !== lastParams.current.R_earth
      ) {
         // Recalculate field lines
         const lines = [];
         for (let angleDeg = 0; angleDeg < 360; angleDeg += 7.5) {
            const angle = (angleDeg * Math.PI) / 180;
            const x0 = R_earth * Math.cos(angle);
            const y0 = R_earth * Math.sin(angle);
            const forward = traceFieldLine(x0, y0, 1, bExtX, bExtY, R_earth);
            const backward = traceFieldLine(x0, y0, -1, bExtX, bExtY, R_earth);
            if (forward.length < 2 && backward.length < 2) continue;
            const fullLine = [...backward.reverse().slice(0, -1), ...forward];
            lines.push(fullLine);
         }
         fieldLinesCache.current = lines;
         lastParams.current = { bExtX, bExtY, R_earth };
      }

      const linesToDraw = fieldLinesCache.current;
      if (!linesToDraw) return; // safety

      // 4. Render Magnetic Field Lines using cached trace values
      ctx.save();
      ctx.translate(cx, cy);

      const stormColor = intensity < 0.35
        ? "rgba(56, 189, 248, 0.42)"
        : intensity < 0.7
          ? "rgba(245, 158, 11, 0.5)"
          : "rgba(239, 68, 68, 0.65)";

      // Draw each cached field line
      linesToDraw.forEach((fullLine) => {
         if (fullLine.length < 2) return;

         ctx.beginPath();
         ctx.moveTo(fullLine[0].x, fullLine[0].y);
         for (let i = 1; i < fullLine.length; i++) {
            ctx.lineTo(fullLine[i].x, fullLine[i].y);
         }

         // Style based on line topology (re-entering Earth = closed; escaping = open)
         const lastPt = fullLine[fullLine.length - 1];
         const lastDist = Math.hypot(lastPt.x, lastPt.y);
         const closed = lastDist < R_earth * 1.05;

         ctx.strokeStyle = closed ? stormColor : "rgba(100, 140, 255, 0.18)";
         ctx.lineWidth = closed ? 1.0 : 0.75;

         // Reconnected IMF field line highlight
         // Note: We are skipping the angle-based highlight for simplicity in this optimization.
         // The highlight is a minor visual effect and can be added back if needed by storing angle with each line.
         // For now, we omit it to keep the change safe and focused on performance.

         ctx.stroke();
      });

      ctx.restore();

      // 5. Draw Orbit Ring (Geostationary equatorial path as projected ellipse)
      ctx.beginPath();
      const rx = R_earth * 5.2;
      const ry = R_earth * 5.2 * Math.sin(20 * Math.PI / 180); // Tilted perspective
      ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(14, 165, 233, 0.25)";
      ctx.lineWidth = 0.8;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      // 6. Draw GOES Satellites along the orbital path
      const time = Date.now() * 0.0006;
      const satAngles = [time, time + Math.PI];
      const satNames = ["GOES-16", "GOES-18"];

      satAngles.forEach((angle, idx) => {
        const satX = rx * Math.cos(angle);
        const satY = ry * Math.sin(angle);
        const isBehind = Math.sin(angle) < 0;

        ctx.save();
        ctx.translate(satX, satY);
        ctx.globalAlpha = isBehind ? 0.35 : 1.0;

        // Satellite Body
        ctx.fillStyle = "#d4af37";
        ctx.fillRect(-4, -4, 8, 8);

        // Solar panels
        ctx.fillStyle = "#1e40af";
        ctx.fillRect(-12, -2, 6, 4);
        ctx.fillRect(6, -2, 6, 4);

        // Antenna
        ctx.strokeStyle = "#e2e8f0";
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(0, -6);
        ctx.stroke();

        ctx.restore();

        // Downlink beam to Earth (only if in front)
        if (!isBehind) {
          ctx.beginPath();
          ctx.moveTo(satX, satY);
          ctx.lineTo(0, 0);
          ctx.strokeStyle = intensity < 0.35 
            ? "rgba(34, 197, 94, 0.25)" 
            : intensity < 0.7 
              ? "rgba(245, 158, 11, 0.35)" 
              : "rgba(239, 68, 68, 0.45)";
          ctx.setLineDash([2, 3]);
          ctx.lineWidth = 0.75;
          ctx.stroke();
          ctx.setLineDash([]);
        }

        // Sat Label
        ctx.fillStyle = isBehind ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.5)";
        ctx.font = "8px monospace";
        ctx.fillText(satNames[idx], satX - 18, satY + 12);
      });

      // 7. Render Earth Circle
      ctx.beginPath();
      ctx.arc(0, 0, R_earth, 0, Math.PI * 2);
      ctx.fillStyle = "#090d16";
      ctx.fill();
      ctx.strokeStyle = "#2e3b56";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Earth detail lines (day/night terminator shadow)
      ctx.beginPath();
      ctx.arc(0, 0, R_earth, -Math.PI / 2, Math.PI / 2);
      ctx.fillStyle = "rgba(0, 0, 0, 0.65)";
      ctx.fill();

      // Magnetic poles indicators (Tilted magnetic poles)
      const poleX = R_earth * Math.sin(DIPOLE_TILT);
      const poleY = R_earth * Math.cos(DIPOLE_TILT);

      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 0.5;
      // North Pole tick
      ctx.beginPath(); ctx.moveTo(poleX, -poleY); ctx.lineTo(poleX * 1.15, -poleY * 1.15); ctx.stroke();
      // South Pole tick
      ctx.beginPath(); ctx.moveTo(-poleX, poleY); ctx.lineTo(-poleX * 1.15, poleY * 1.15); ctx.stroke();

      // 8. Draw Polar Auroras (green/red dancing bands expanding based on storm severity)
      const aurIntensity = Math.min(1.0, intensity);
      const aurRad = R_earth * (0.35 + 0.35 * aurIntensity);
      const aurY = R_earth * (0.94 - 0.16 * aurIntensity);

      ctx.save();
      ctx.rotate(DIPOLE_TILT);
      
      const aurColor = intensity < 0.35 
        ? "rgba(34, 197, 94, 0.5)" 
        : intensity < 0.7 
          ? "rgba(234, 179, 8, 0.65)" 
          : "rgba(236, 72, 153, 0.85)";

      ctx.strokeStyle = aurColor;
      ctx.shadowColor = aurColor;
      ctx.shadowBlur = 6;
      ctx.lineWidth = 2.0;

      // Dancing polar waves
      ctx.beginPath();
      for (let theta = 0; theta <= Math.PI * 2; theta += 0.1) {
        const wave = 2.5 * Math.sin(time * 6.0 + theta * 8.0) * aurIntensity;
        const x = (aurRad + wave) * Math.cos(theta);
        const y = -aurY + wave * 0.4;
        if (theta === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.beginPath();
      for (let theta = 0; theta <= Math.PI * 2; theta += 0.1) {
        const wave = 2.5 * Math.cos(time * 6.0 + theta * 8.0) * aurIntensity;
        const x = (aurRad + wave) * Math.cos(theta);
        const y = aurY + wave * 0.4;
        if (theta === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      ctx.restore();
      ctx.restore();

      // 9. Draw Bow Shock Line Front
      ctx.beginPath();
      for (let y = 0; y <= height; y += 5) {
        const x = cx - R_shock - curvature * Math.pow(y - cy, 2);
        if (y === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = intensity < 0.35 
        ? "rgba(14, 165, 233, 0.75)" 
        : intensity < 0.7 
          ? "rgba(245, 158, 11, 0.85)" 
          : "rgba(239, 68, 68, 0.95)";
      ctx.lineWidth = intensity > 0.7 ? 1.5 : 1.0;
      ctx.stroke();

      // 10. Update & Render Solar Wind Particles
      ctx.fillStyle = intensity < 0.35 
        ? "rgba(14, 165, 233, 0.6)" 
        : intensity < 0.7 
          ? "rgba(245, 158, 11, 0.7)" 
          : "rgba(239, 68, 68, 0.85)";

      const baseWindSpeed = 0.8 + 1.2 * (speed / 400.0);

      particles.forEach((p) => {
        // Move particle rightward
        p.x += p.speed * baseWindSpeed;

        const shockX = cx - R_shock - curvature * Math.pow(p.y - cy, 2);

        // Sheath deflection boundary collision
        if (p.x > shockX) {
          p.deflected = true;
          const dy = p.y - cy;
          // Calculate tangent direction along parabola
          const tx = -2.0 * curvature * dy;
          const ty = 1.0;
          const tl = Math.hypot(tx, ty);
          const nx = tx / tl;
          const ny = ty / tl;

          const deflSpeed = p.speed * 0.35; // Slow down inside sheath boundary
          const flowDir = dy >= 0 ? 1.0 : -1.0;
          p.x += nx * deflSpeed * flowDir;
          p.y += ny * deflSpeed * flowDir;
        }

        // Reset particles exiting the canvas
        if (p.x > width || p.y < 0 || p.y > height) {
          p.x = -10;
          p.y = Math.random() * height;
          p.deflected = false;
        }

        ctx.globalAlpha = p.opacity;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1.0;

      // Request next frame
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", resizeCanvas);
    };
  }, []);

  // Ambient Backlighting Color Mappings
  const getAmbientBacklight = () => {
    const intensity = data.intensity;
    if (intensity < 0.35) {
      return "radial-gradient(circle at 10% 50%, rgba(14, 165, 233, 0.12) 0%, rgba(3, 5, 8, 0) 65%)";
    } else if (intensity < 0.7) {
      return "radial-gradient(circle at 10% 50%, rgba(251, 191, 36, 0.16) 0%, rgba(3, 5, 8, 0) 70%)";
    } else {
      return "radial-gradient(circle at 10% 50%, rgba(239, 68, 68, 0.22) 0%, rgba(3, 5, 8, 0) 75%)";
    }
  };

  const getBorderColor = () => {
    const intensity = data.intensity;
    if (intensity < 0.35) return "border-[#2a3038]/40";
    if (intensity < 0.7) return "border-[#fbbf24]/40";
    return "border-[#ef4444]/60 animate-pulse";
  };

  return (
    <div
      className={`relative w-full h-full flex flex-col overflow-hidden rounded-2xl border transition-all duration-700 ${getBorderColor()}`}
      style={{
        background: "#05070a",
        boxShadow: "0 4px 30px rgba(0, 0, 0, 0.4)"
      }}
    >
      <div 
        className="absolute inset-0 pointer-events-none transition-all duration-700" 
        style={{ background: getAmbientBacklight() }}
      />

      {/* 2D Canvas Container */}
      <div ref={containerRef} className="flex-1 w-full h-full min-h-0 relative z-0">
        <canvas ref={canvasRef} className="block" />
      </div>

      {/* Header Overlay HUD Panel */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-start pointer-events-none z-10">
        <div className="flex flex-col gap-1">
          <span className="text-[9px] font-mono text-white/30 tracking-widest uppercase font-bold">
            NOAA Space Weather Simulation (2D Meridian plane)
          </span>
          <h2 className={`text-base font-extrabold tracking-tight transition-colors duration-500 flex items-center gap-1.5 ${
            data.intensity < 0.35 
              ? "text-sky-400" 
              : data.intensity < 0.7 
                ? "text-amber-400" 
                : "text-rose-500"
          }`}>
            <Zap size={14} className={data.intensity > 0.7 ? "animate-bounce" : "animate-pulse"} />
            {data.state.toUpperCase()}
          </h2>
        </div>

        {/* Live status telemetry bubble */}
        <div className={`px-2.5 py-1 rounded-full border text-[9px] font-mono font-bold flex items-center gap-1.5 pointer-events-auto cursor-pointer select-none transition-all ${
          isLive && !useManual
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
            : "bg-white/3 border-white/10 text-white/50"
        }`}
          onClick={() => {
            if (isLive) setUseManual(false);
          }}
          title={isLive ? "Connected to live FastAPI telemetry WebSocket" : "FastAPI server offline."}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${isLive && !useManual ? "bg-emerald-400 animate-ping" : "bg-white/30"}`} />
          {isLive && !useManual ? "NASA/NOAA LIVE FEED" : "MOCK SIMULATOR"}
        </div>
      </div>

      {/* HUD Telemetry stats (shows real physical values driving the canvas!) */}
      <div className="absolute top-16 left-4 flex flex-col gap-2 pointer-events-none z-10 font-mono text-[9px] text-white/45 bg-[#10141a]/85 p-2.5 rounded-lg border border-[#2a3038]/60 backdrop-blur-sm">
        <div className="flex justify-between gap-6">
          <span className="text-white/20">WIND SPEED:</span>
          <span className="font-bold text-amber-400">{data.wind_speed.toFixed(1)} km/s</span>
        </div>
        <div className="flex justify-between gap-6">
          <span className="text-white/20">DENSITY:</span>
          <span className="font-bold text-purple-400">{data.density.toFixed(1)} N/cm³</span>
        </div>
        <div className="flex justify-between gap-6">
          <span className="text-white/20">IMF BZ:</span>
          <span className={`font-bold ${data.bz < -4.0 ? "text-rose-400" : "text-emerald-400"}`}>
            {data.bz.toFixed(1)} nT
          </span>
        </div>
        <div className="flex justify-between gap-6">
          <span className="text-white/20">DYN PRESSURE:</span>
          <span className="font-bold text-white">{data.dynamic_pressure.toFixed(2)} nPa</span>
        </div>
        <div className="flex justify-between gap-6">
          <span className="text-white/20">STANDOFF R_mp:</span>
          <span className="font-bold text-sky-400">{data.scaling_factor.toFixed(2)} RE</span>
        </div>
      </div>

      {/* Dynamic Overlay HUD Labels pointing to features */}
      <div className="absolute inset-0 pointer-events-none z-5">
        {/* Day Side (left) Compression Label */}
        <div className="absolute left-[8%] top-[62%] -translate-y-1/2 flex flex-col items-start gap-1 font-mono text-[8px]">
          <span className="text-white/20 uppercase font-semibold">IMF lines</span>
          <div className="h-[1px] w-8 bg-white/20" />
          <span className={`transition-colors duration-500 ${
            data.bz < -4.0 
              ? "text-rose-400/50" 
              : "text-sky-400/50"
          }`}>
            Deflected front
          </span>
        </div>

        {/* Bow Shock shield Label */}
        <div className="absolute left-[20%] top-[24%] flex flex-col items-start gap-1 font-mono text-[8px]">
          <span className={`transition-colors duration-500 uppercase font-bold ${
            data.intensity < 0.35 
              ? "text-sky-400/80" 
              : data.intensity < 0.7 
                ? "text-amber-400/80" 
                : "text-rose-500/90"
          }`}>
            Bow Shock
          </span>
          <div className="h-[1px] w-6 bg-white/30" />
          <span className="text-white/30 font-semibold">
            {data.intensity > 0.7 ? "Heavily Compressed" : "Stable Boundary"}
          </span>
        </div>

        {/* Magnetotail Reconnection Label */}
        <div className="absolute right-[12%] bottom-[28%] flex flex-col items-end gap-1 font-mono text-[8px]">
          <span className="text-white/20 uppercase font-semibold">Magnetotail</span>
          <div className="h-[1px] w-12 bg-white/20" />
          <span className={`transition-colors duration-500 ${
            data.bz < -8.0 
              ? "text-rose-400/80 font-bold" 
              : "text-sky-400/50"
          }`}>
            {data.bz < -8.0 ? "Magnetic Reconnection" : "Alfvén Waves"}
          </span>
        </div>
      </div>

      {/* Manual Override controls drawer at the bottom */}
      <div className="absolute bottom-4 left-4 right-4 bg-[#10141a]/90 border border-[#2a3038]/60 p-3 rounded-xl flex items-center justify-between gap-6 z-10 pointer-events-auto backdrop-blur-md">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setUseManual(!useManual)}
            className={`p-2 rounded-lg cursor-pointer transition-all flex items-center justify-center ${
              useManual 
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/30" 
                : "bg-white/5 border border-white/10 text-white/70 hover:bg-white/10"
            }`}
            title={useManual ? "Click to return to live NASA feed" : "Click to manually override storm parameters"}
          >
            {useManual ? <RefreshCw size={12} className="animate-spin" /> : <Compass size={12} />}
          </button>
          <div className="flex flex-col">
            <span className="text-[10px] font-mono text-white/40 uppercase">Interactive Testing</span>
            <span className="text-[11px] font-bold text-white/80">
              {useManual ? "Slider Override Active" : "NOAA Live Feed Active"}
            </span>
          </div>
        </div>

        {/* Override Slider */}
        <div className="flex-1 flex items-center gap-3 max-w-[220px]">
          <span className="text-[10px] font-mono text-sky-400">Calm</span>
          <input
            type="range"
            min="0.05"
            max="0.98"
            step="0.01"
            value={useManual ? manualIntensity : data.intensity}
            onChange={(e) => {
              setUseManual(true);
              setManualIntensity(parseFloat(e.target.value));
            }}
            className="flex-1 h-1 bg-white/15 rounded-lg appearance-none cursor-pointer accent-[#0ea5e9] focus:outline-none"
          />
          <span className="text-[10px] font-mono text-rose-400">Severe</span>
        </div>

        {/* Real-time stats display */}
        <div className="flex gap-4 pr-1 text-right">
          <div className="flex flex-col">
            <span className="text-[9px] font-mono text-white/30 uppercase">Intensity</span>
            <span className={`text-[11px] font-bold font-mono ${
              data.intensity < 0.35 
                ? "text-sky-400" 
                : data.intensity < 0.7 
                  ? "text-amber-400" 
                  : "text-rose-500"
            }`}>
              {data.intensity.toFixed(2)}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] font-mono text-white/30 uppercase">Compression</span>
            <span className="text-[11px] font-bold font-mono text-white">
              {((1.0 - data.scaling_factor) * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>
      
    </div>
  );
}
