import { useEffect, useRef, useState } from "react";
import { Zap } from "lucide-react";
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

const INITIAL_DATA: SpaceWeatherPhysicsData = {
  intensity: 0.15,
  state: "Calm Conditions",
  scaling_factor: 0.9,
  wind_speed: 400.0,
  density: 5.0,
  bz: 1.5,
  dynamic_pressure: 1.6,
  timestamp: Date.now() / 1000,
  live: false,
};

interface Particle {
  x: number;
  y0: number; // original entry height
  y: number;  // current height
  vx: number;

  type: "proton" | "electron" | "cosmic_ray";

  size: number;
  opacity: number;

  mode: "stream" | "cusp" | "belt";
  angle?: number;
  cuspTarget?: number;
  cuspProgress?: number;
  captureX?: number;
  captureY?: number;
}

const getStormTextClass = (intensity: number) => {
  if (intensity < 0.35) return "text-sky-400";
  if (intensity < 0.7) return "text-amber-400";
  return "text-rose-500";
};

export function FreshEarthVisualizer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const physicsRef = useRef<SpaceWeatherPhysicsData>(INITIAL_DATA);

  const [data, setData] = useState<SpaceWeatherPhysicsData>(INITIAL_DATA);
  const [connectionMode, setConnectionMode] = useState<"websocket" | "polling" | "offline">("offline");

  useEffect(() => {
    physicsRef.current = data;
  }, [data]);

  // Telemetry connection
  useEffect(() => {
    let socket: WebSocket | null = null;
    let pollInterval: NodeJS.Timeout | null = null;
    let reconnectTimeout: NodeJS.Timeout | null = null;
    let disposed = false;

    const fetchSnapshot = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/regression-intensity`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload: SpaceWeatherPhysicsData = await response.json();
        if (disposed) return;
        setData(payload);
        setConnectionMode("polling");
      } catch {
        if (!disposed) setConnectionMode("offline");
      }
    };

    const startPolling = () => {
      if (pollInterval) return;
      void fetchSnapshot();
      pollInterval = setInterval(fetchSnapshot, 5000);
    };

    const stopPolling = () => {
      if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
      }
    };

    const connectWebSocket = () => {
      stopPolling();
      try {
        socket = new WebSocket(`${WS_BASE}/ws/intensity`);

        socket.onopen = () => {
          if (!disposed) setConnectionMode("websocket");
        };

        socket.onmessage = (event) => {
          try {
            const payload: SpaceWeatherPhysicsData = JSON.parse(event.data);
            if (!disposed) {
              setData(payload);
              setConnectionMode("websocket");
            }
          } catch {
            if (!disposed) setConnectionMode("polling");
          }
        };

        socket.onerror = () => {
          socket?.close();
        };

        socket.onclose = () => {
          if (disposed) return;
          setConnectionMode("polling");
          startPolling();
          reconnectTimeout = setTimeout(connectWebSocket, 7000);
        };
      } catch {
        setConnectionMode("polling");
        startPolling();
      }
    };

    connectWebSocket();

    return () => {
      disposed = true;
      socket?.close();
      stopPolling();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // 2D High-Performance Physics Diagram Simulation
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

    const DIPOLE_TILT = (11.5 * Math.PI) / 180;

    // Initialize Solar Wind particles pool
    const particles: Particle[] = [];

    const createParticle = () : Particle => {
      const r = Math.random();
      const type = r < 0.45 ? "proton" : r < 0.9 ? "electron" : "cosmic_ray";
      return {
        x: -50,
        y0: -20 + Math.random() * (height + 40),
        y: 0,
        vx: 2 + Math.random()*3,
        type,
        size: type === "proton" ? 2.5 : type === "electron" ? 1.5 : 2.0,
        opacity: .5 + Math.random()*0.5,
        mode: "stream"
      };
    };

    const render = () => {
      const p = physicsRef.current;
      const intensity = p.intensity;
      const scaling = p.scaling_factor;
      const speed = p.wind_speed;
      const bz = p.bz;

      ctx.clearRect(0, 0, width, height);

      // Define coordinate system relative to Earth center
      const cx = width * 0.62; // Earth shifted slightly to the left to give magnetotail breathing space
      const cy = height * 0.5;
      const R_earth = Math.min(width, height) * 0.088;

      // Sun coordinate system on the left
      const cx_sun = -width * 0.15;
      const R_sun = height * 0.44;

      const breathing = Math.sin(Date.now() * 0.0035) * (1.5 + intensity * 3.5);
      const R_shock = R_earth * 2.35 * scaling + breathing;
      const curvature = 0.0048 / (scaling * 0.85);

      // Scale dipole moment dynamically to maintain visual balance relative to R_earth
      const DIPOLE_MOMENT = Math.pow(R_earth, 3) * 32.0;

      // Check if telemetry values exceed warning threshold
      const isAboveThreshold = intensity >= 0.35;

      // 1. Background sky/space gradient (light blue on left to black space on right)
      const gradBg = ctx.createLinearGradient(0, 0, width, 0);
      gradBg.addColorStop(0, "#083344");   // Deep blue/cyan near the sun
      gradBg.addColorStop(0.38, "#020617"); // Dark outer space
      gradBg.addColorStop(1, "#020617");
      ctx.fillStyle = gradBg;
      ctx.fillRect(0, 0, width, height);

      // 2. Streamline Deflection Physics (Continuous, smooth Asymmetric Bi-Gaussian deflection)
      const getDeflectedY = (x: number, y0: number) => {
        const dy = y0 - cy;
        const sign = Math.sign(dy) || 1;
        const absDy = Math.abs(dy);
        
        // Peak deflection is centered just in front of Earth (dayside magnetopause)
        const peakX = cx - R_earth * 0.4;
        
        // Asymmetric widths: sharp deflection at the front, slow tapering (closure) at the back
        const sigmaX = x < peakX 
          ? R_shock * 1.1  // Dayside entry curve
          : R_shock * 2.3; // Nightside tail closure
          
        const xDiff = x - peakX;
        const xFactor = Math.exp(-(xDiff * xDiff) / (2 * sigmaX * sigmaX));
        
        // Equator lines deflect more, polar lines deflect less (hugs magnetosphere closely)
        const sigmaY = R_earth * 2.36;
        const yFactor = Math.exp(-absDy / sigmaY);
        
        // Push the lines smoothly outward, scaled by dynamic pressure (tweak 3: impact bending)
        const push = R_shock * 0.98 * xFactor * yFactor * (0.8 + (p.dynamic_pressure / 5.0) * 0.4);
        
        return y0 + push * sign;
      };

      // 3. Draw Smoky Solar Wind Plasma (glowing gas ribbons deflecting around Earth)
      const drawSmokySolarWind = (time: number, intensity: number, speed: number) => {
        ctx.save();
        
        const ribbonCount = 12;
        const baseSpeed = 0.0035 * (speed / 400.0);
        
        // Setup glow color based on storm intensity (amber-yellow to hot red-orange)
        const calmColor = "rgba(251, 191, 36, 0.05)";  // Golden amber, very soft
        const stormColor = "rgba(249, 115, 22, 0.12)";  // Hot orange
        const activeColor = "rgba(239, 68, 68, 0.18)";  // Severe red
        
        const strokeColor = intensity < 0.35 
          ? calmColor 
          : intensity < 0.7 
            ? stormColor 
            : activeColor;

        ctx.strokeStyle = strokeColor;
        // Ribbon thickness increases with storm intensity
        ctx.lineWidth = 16 + intensity * 24;
        ctx.lineCap = "round";
        
        // Add shadow blur for a real smoky gaseous glow
        ctx.shadowBlur = 10 + intensity * 15;
        ctx.shadowColor = intensity < 0.35 ? "#f59e0b" : "#ef4444";

        for (let i = 0; i < ribbonCount; i++) {
          const y0 = cy - height * 0.52 + (height * 1.04 * (i + 0.5)) / ribbonCount;
          
          ctx.beginPath();
          let first = true;
          
          for (let x = 12; x <= width; x += 12) {
            let y = getDeflectedY(x, y0);
            
            // Low-frequency, low-amplitude wave for smooth laminar flow, preventing snake-like wiggles
            const waveFreq = 0.006;
            const waveAmplitude = 1.8 + intensity * 3.5;
            y += Math.sin(x * waveFreq - time * baseSpeed + i) * waveAmplitude;
            
            if (first) {
              ctx.moveTo(x, y);
              first = false;
            } else {
              ctx.lineTo(x, y);
            }
          }
          ctx.stroke();
        }
        
        ctx.restore();
      };
      drawSmokySolarWind(Date.now(), intensity, speed);

      // 4. Solar Wind Sheath Layer (Soft crescent glow, no hard lines)
      ctx.save();
      ctx.beginPath();
      for (let y = -20; y <= height + 20; y += 10) {
        const x = cx - R_shock - curvature * Math.pow(y - cy, 2);
        if (y === -20) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }

      const sheathGlow = ctx.createLinearGradient(cx - R_shock - 40, cy, cx - R_shock + 60, cy);
      if (intensity < 0.35) {
        sheathGlow.addColorStop(0, "rgba(249, 115, 22, 0.0)");
        sheathGlow.addColorStop(0.4, "rgba(249, 115, 22, 0.20)");
        sheathGlow.addColorStop(1, "rgba(249, 115, 22, 0.0)");
      } else {
        sheathGlow.addColorStop(0, "rgba(239, 68, 68, 0.0)");
        sheathGlow.addColorStop(0.4, "rgba(239, 68, 68, 0.40)");
        sheathGlow.addColorStop(1, "rgba(239, 68, 68, 0.0)");
      }
      ctx.strokeStyle = sheathGlow;
      ctx.lineWidth = 70 + intensity * 60;
      ctx.stroke();
      ctx.restore();

      // 6. Recalculate and Draw Earth's Dipolar Magnetosphere Field Lines
      const drawMagnetosphereLines = (intensity: number, scaling: number) => {
        const loopsCount = 6;
        const compression = scaling; // scaling represents dayside magnetopause distance (0.38 - 1.25)
        
        ctx.save();
        ctx.translate(cx, cy);
        
        let fieldLineColor = "rgba(56, 189, 248, 0.45)"; // Calm sky blue
        if (intensity >= 0.7) {
          fieldLineColor = "rgba(244, 63, 94, 0.85)"; // Severe storm: Bright Rose/Red
        } else if (intensity >= 0.35) {
          fieldLineColor = "rgba(245, 158, 11, 0.68)"; // Moderate storm: Glowing Amber
        }
        
        ctx.strokeStyle = fieldLineColor;
        ctx.lineWidth = 1.2;
        
        // Tilt the magnetic dipole axis slightly relative to Y-axis
        ctx.rotate(DIPOLE_TILT);
        
        for (let i = 1; i <= loopsCount; i++) {
          const L_base = R_earth * (0.8 + i * 0.28);
          
          // Draw left loop (dayside - compressed by solar wind)
          ctx.beginPath();
          for (let step = 0; step <= 50; step++) {
            const theta = (step / 50) * Math.PI; // 0 to pi
            const r = L_base * Math.sin(theta) * Math.sin(theta);
            
            // Left side loop (negative X) - compressed even more at the front nose (tweak 2)
            const x_dip = -r * Math.sin(theta) * compression * 0.82;
            const y_dip = r * Math.cos(theta);
            
            if (step === 0) ctx.moveTo(x_dip, y_dip);
            else ctx.lineTo(x_dip, y_dip);
          }
          ctx.stroke();
          
          // Draw right loop (nightside - stretched tail)
          ctx.beginPath();
          for (let step = 0; step <= 50; step++) {
            const theta = (step / 50) * Math.PI;
            const r = L_base * Math.sin(theta) * Math.sin(theta);
            
            // Right side loop (positive X) - increased X stretch behind Earth (tweak 2)
            const stretch = 1.0 + (i * 0.65) * Math.sin(theta);
            const x_dip = r * Math.sin(theta) * stretch;
            const y_dip = r * Math.cos(theta);
            
            if (step === 0) ctx.moveTo(x_dip, y_dip);
            else ctx.lineTo(x_dip, y_dip);
          }
          ctx.stroke();
        }
        ctx.restore();
      };
      drawMagnetosphereLines(intensity, scaling);

      // 7. Draw Earth Globe (Styled vectors)
      ctx.save();
      ctx.translate(cx, cy);

      ctx.beginPath();
      ctx.arc(0, 0, R_earth, 0, Math.PI * 2);
      ctx.fillStyle = "#1d4ed8";
      ctx.fill();

      ctx.beginPath();
      ctx.arc(0, 0, R_earth, 0, Math.PI * 2);
      ctx.clip();

      // Americas green continent
      ctx.fillStyle = "#22c55e";
      ctx.beginPath();
      ctx.moveTo(-R_earth * 0.8, -R_earth * 0.5);
      ctx.lineTo(-R_earth * 0.2, -R_earth * 0.1);
      ctx.lineTo(-R_earth * 0.45, R_earth * 0.35);
      ctx.lineTo(-R_earth * 0.15, R_earth * 0.6);
      ctx.lineTo(-R_earth * 0.6, R_earth * 0.82);
      ctx.lineTo(-R_earth * 0.9, R_earth * 0.1);
      ctx.closePath();
      ctx.fill();

      // Africa / Europe green continent
      ctx.beginPath();
      ctx.moveTo(R_earth * 0.05, -R_earth * 0.75);
      ctx.lineTo(R_earth * 0.65, -R_earth * 0.45);
      ctx.lineTo(R_earth * 0.4, R_earth * 0.15);
      ctx.lineTo(R_earth * 0.72, R_earth * 0.45);
      ctx.lineTo(R_earth * 0.25, R_earth * 0.85);
      ctx.lineTo(-R_earth * 0.02, R_earth * 0.2);
      ctx.closePath();
      ctx.fill();

      // Polar Caps
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(0, -R_earth * 1.0, R_earth * 0.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(0, R_earth * 1.0, R_earth * 0.4, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.arc(0, 0, R_earth, -Math.PI / 2, Math.PI / 2);
      ctx.fillStyle = "rgba(0, 0, 0, 0.48)";
      ctx.fill();

      ctx.restore();

      // 8. Draw Sun on the Left (Radial glow)
      const gradSun = ctx.createRadialGradient(
        cx_sun + R_sun * 0.4, cy, 0,
        cx_sun + R_sun * 0.4, cy, R_sun
      );
      gradSun.addColorStop(0, "#ffffff");
      gradSun.addColorStop(0.18, "#fef08a");
      gradSun.addColorStop(0.48, "#f97316");
      gradSun.addColorStop(0.85, "rgba(239, 68, 68, 0.22)");
      gradSun.addColorStop(1.0, "rgba(239, 68, 68, 0)");
      ctx.fillStyle = gradSun;
      ctx.beginPath();
      ctx.arc(cx_sun + R_sun * 0.4, cy, R_sun, 0, Math.PI * 2);
      ctx.fill();

      // 9. Draw active Solar Flare (If storm intensity is elevated)
      if (intensity > 0.42) {
        ctx.beginPath();
        const loopRadius = R_sun * 0.24;
        ctx.arc(cx_sun + R_sun * 1.12, cy, loopRadius, -0.42, 0.42);
        ctx.strokeStyle = "rgba(251, 146, 60, 0.88)";
        ctx.lineWidth = 3.0;
        ctx.stroke();

        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.0;
        ctx.stroke();

        ctx.fillStyle = "rgba(251, 146, 60, 0.8)";
        ctx.font = "italic 8.5px sans-serif";
        ctx.fillText("Solar flare", cx_sun + R_sun * 1.34, cy - 8);
      }

      // 10. Draw and Transport Solar Wind Particles Pool
      const activeCount = Math.min(80, Math.max(16, Math.round(p.density * 2.5)));
      while (particles.length < activeCount) {
        particles.push({
          x: cx_sun + R_sun * 0.95 + Math.random() * (cx - cx_sun),
          y0: -20 + Math.random() * (height + 40),
          y: 0,
          vx: 1.2 + Math.random() * 1.6,
          size: Math.random() < 0.5 ? 2.5 : 1.5,
          opacity: 0.4 + Math.random() * 0.5,
          type: Math.random() < 0.4 ? "proton" : Math.random() < 0.85 ? "electron" : "cosmic_ray",
          mode: "stream"
        });
      }

      // Base speed gets accelerated during storm events to make the storm feel active (tweak 4)
      const baseWindSpeed = 1.4 * (speed / 400.0) * (1.0 + intensity * 3.0);
      particles.forEach((p) => {
        if (p.mode === "stream") {
          p.x += p.vx * baseWindSpeed;
          if (p.type === "cosmic_ray") {
            p.y = p.y0; // Cosmic rays (neutral) go straight
          } else {
            p.y = getDeflectedY(p.x, p.y0);
            
            // Check for capture into belt or cusp
            const distToEarth = Math.hypot(p.x - cx, p.y - cy);
            if (distToEarth < R_shock * 1.15 && distToEarth > R_earth * 1.1) {
              const angleToEarth = Math.atan2(p.y - cy, p.x - cx);
              const absAngle = Math.abs(angleToEarth);
              const isNearCusp = Math.abs(absAngle - Math.PI / 2) < 0.28;

              const captureCuspProb = bz < 0 ? 0.08 : 0.02;
              if (isNearCusp && Math.random() < captureCuspProb) {
                p.mode = "cusp";
                p.cuspTarget = angleToEarth > 0 ? 1 : -1;
                p.cuspProgress = 0;
                p.captureX = p.x;
                p.captureY = p.y;
              } else if (
                distToEarth < R_earth * 4.6 &&
                distToEarth > R_earth * 2.8 &&
                Math.abs(p.y - cy) < R_earth * 1.2
              ) {
                const captureBeltProb = bz < 0 ? 0.04 : 0.02;
                if (Math.random() < captureBeltProb) {
                  p.mode = "belt";
                  p.angle = angleToEarth;
                }
              }
            }
          }

          if (p.x > width) {
            Object.assign(p, createParticle());
          }
        } else if (p.mode === "cusp") {
          // Spiraling into magnetic poles
          const targetPoleY = p.cuspTarget === 1
            ? cy + R_earth * Math.cos(DIPOLE_TILT) * 0.9
            : cy - R_earth * Math.cos(DIPOLE_TILT) * 0.9;
          const targetPoleX = p.cuspTarget === 1
            ? cx - R_earth * Math.sin(DIPOLE_TILT) * 0.9
            : cx + R_earth * Math.sin(DIPOLE_TILT) * 0.9;

          p.cuspProgress = (p.cuspProgress || 0) + 0.024 * baseWindSpeed;

          if (p.cuspProgress >= 1.0) {
            Object.assign(p, createParticle());
          } else {
            const startX = p.captureX ?? p.x;
            const startY = p.captureY ?? p.y;

            const wobble = 3.5 * Math.sin(p.cuspProgress * Math.PI * 6.5) * (1 - p.cuspProgress);
            const rawX = startX + (targetPoleX - startX) * p.cuspProgress;
            const rawY = startY + (targetPoleY - startY) * p.cuspProgress;

            const dx = targetPoleX - startX;
            const dy = targetPoleY - startY;
            const len = Math.hypot(dx, dy);
            const perpX = -dy / (len || 1);
            const perpY = dx / (len || 1);

            p.x = rawX + perpX * wobble;
            p.y = rawY + perpY * wobble;
          }
        } else if (p.mode === "belt") {
          // Van Allen belt orbit
          const r_orbit = Math.hypot(p.x - cx, p.y - cy);
          p.angle = (p.angle ?? 0) + 0.024 * (speed / 400.0) * (R_earth / (r_orbit || 1));

          p.x = cx + r_orbit * Math.cos(p.angle);
          p.y = cy + r_orbit * Math.sin(p.angle);

          if (Math.random() < 0.003) {
            Object.assign(p, createParticle());
          }
        }

        // Draw particle
        ctx.globalAlpha = p.opacity;
        if (p.type === "proton") {
          ctx.fillStyle = "#ff3030";
        } else if (p.type === "electron") {
          ctx.fillStyle = "#ffe600";
          ctx.shadowBlur = 15;
          ctx.shadowColor = "#ffff00";
        } else if (p.type === "cosmic_ray") {
          ctx.fillStyle = "#ffffff";
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      });
      ctx.globalAlpha = 1.0;

      // 11. Diagram labels (Matches the uploaded reference image)
      ctx.save();

      // SOLAR WIND header label at the top
      ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
      ctx.font = "bold 13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("SOLAR WIND", width * 0.5, 34);

      // Earth's magnetic field label
      ctx.fillStyle = "rgba(255, 255, 255, 0.65)";
      ctx.font = "9px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText("Earth's magnetic field", cx - R_earth * 1.15, cy - R_earth * 2.3);

      ctx.strokeStyle = "rgba(255, 255, 255, 0.38)";
      ctx.lineWidth = 0.65;
      ctx.beginPath();
      ctx.moveTo(cx - R_earth * 0.3, cy - R_earth * 2.18);
      ctx.lineTo(cx - R_earth * 0.1, cy - R_earth * 1.45);
      ctx.stroke();

      // Solar wind stream label
      ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
      ctx.font = "italic 9.5px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Solar wind", cx_sun + R_sun * 1.82, cy - R_earth * 2.2);

      // Bow Shock label
      ctx.fillStyle = getStormTextClass(intensity);
      ctx.font = "bold 9.5px sans-serif";
      ctx.textAlign = "right";
      ctx.fillText("Bow Shock", cx - R_shock - 18, cy - R_earth * 3.4);

      ctx.restore();

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", resizeCanvas);
    };
  }, []);

  const getBorderColor = () => {
    const intensity = data.intensity;
    if (intensity < 0.35) return "border-[#2a3038]/40";
    if (intensity < 0.7) return "border-[#fbbf24]/40";
    return "border-[#ef4444]/60 animate-pulse";
  };

  return (
    <div
      className={`relative w-full h-full flex flex-col overflow-hidden rounded-[24px] border transition-all duration-700 ${getBorderColor()}`}
      style={{
        background: "#05070a",
        boxShadow: "0 10px 40px rgba(0, 0, 0, 0.35)",
      }}
    >
      {/* 2D Canvas Container */}
      <div ref={containerRef} className="flex-1 w-full h-full min-h-0 relative z-0">
        <canvas ref={canvasRef} className="block" />
      </div>

      {/* Header Overlay HUD Panel (Clean, compact, and non-blocking) */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-start pointer-events-none z-10">
        <div className="flex flex-col gap-1 p-2.5 rounded-xl bg-[#070b12]/80 border border-white/5 backdrop-blur-md">
          <span className="text-[8px] font-mono text-white/30 tracking-widest uppercase font-bold px-1">
            SPACE WEATHER WARNING SYSTEM
          </span>
          <h2
            className={`text-xs font-extrabold tracking-tight transition-colors duration-500 flex items-center gap-1.5 px-1 ${getStormTextClass(
              data.intensity
            )}`}
          >
            <Zap size={12} className="animate-pulse" />
            {data.state.toUpperCase()}
          </h2>
        </div>

        {/* Telemetry Status bubble */}
        <div
          className={`px-2.5 py-1.5 rounded-full border border-white/5 text-[8px] font-mono font-bold flex items-center gap-1.5 bg-[#070b12]/80 backdrop-blur-md text-white/70`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              connectionMode === "websocket"
                ? "bg-emerald-400 animate-ping"
                : connectionMode === "polling"
                  ? "bg-amber-400"
                  : "bg-rose-500"
            }`}
          />
          {connectionMode === "websocket"
            ? "LIVE FEED"
            : connectionMode === "polling"
              ? "POLLING FEED"
              : "TELEMETRY OFFLINE"}
        </div>
      </div>
    </div>
  );
}
