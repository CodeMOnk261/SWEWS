import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Zap, Shield, Activity, RefreshCw, Compass } from "lucide-react";

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

export function EarthVisualization() {
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

  // References for WebGL update loop
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
      // Re-map manual slider intensity to physical quantities
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

  // 1. Establish connection to live FastAPI Server (WebSocket + Polling fallback)
  useEffect(() => {
    if (useManual) return;

    let socket: WebSocket | null = null;
    let pollInterval: NodeJS.Timeout | null = null;
    let mockInterval: NodeJS.Timeout | null = null;
    
    const connectWebSocket = () => {
      try {
        socket = new WebSocket("ws://localhost:8000/ws/intensity");
        
        socket.onopen = () => {
          console.log("SWEWS WebGL: WebSocket connected.");
          setIsLive(true);
          if (pollInterval) clearInterval(pollInterval);
          if (mockInterval) clearInterval(mockInterval);
        };
        
        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data);
            setData(payload);
          } catch (err) {
            console.error("SWEWS WebGL: Error parsing WS packet:", err);
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
          const res = await fetch("http://localhost:8000/api/regression-intensity");
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
      
      console.log("SWEWS WebGL: API offline, cycling mock environment.");
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

  // 2. High-Fidelity Three.js WebGL Simulation Setup
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    camera.position.set(0, 0, 11.5); // Side view perspective

    // Lighting config
    const ambientLight = new THREE.AmbientLight(0x0a1024, 0.7);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfff5ea, 3.8);
    sunLight.position.set(-20, 0, 0); // light source from Sun (-X)
    scene.add(sunLight);

    // Procedural Globe Texture
    const createEarthTexture = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 512;
      canvas.height = 256;
      const ctx = canvas.getContext("2d")!;
      
      // Deep sea
      ctx.fillStyle = "#09172c";
      ctx.fillRect(0, 0, 512, 256);
      
      // Continents (greenish-cyan grids)
      ctx.fillStyle = "#154d5c";
      
      // Simple continents math circles
      ctx.beginPath(); ctx.arc(130, 95, 42, 0, Math.PI * 2); ctx.fill(); // NA
      ctx.beginPath(); ctx.arc(165, 172, 33, 0, Math.PI * 2); ctx.fill(); // SA
      ctx.beginPath(); ctx.arc(282, 134, 38, 0, Math.PI * 2); ctx.fill(); // Africa
      ctx.beginPath(); ctx.arc(315, 84, 52, 0, Math.PI * 2); ctx.fill();  // Eurasia
      ctx.beginPath(); ctx.arc(362, 75, 42, 0, Math.PI * 2); ctx.fill();  // Asia
      ctx.beginPath(); ctx.arc(415, 162, 24, 0, Math.PI * 2); ctx.fill(); // Australia

      // Latitude and longitude lines
      ctx.strokeStyle = "rgba(74, 144, 164, 0.14)";
      ctx.lineWidth = 0.5;
      for (let i = 0; i < 512; i += 32) {
        ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 256); ctx.stroke();
      }
      for (let j = 0; j < 256; j += 32) {
        ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(512, j); ctx.stroke();
      }
      
      return new THREE.CanvasTexture(canvas);
    };

    // Earth Sphere
    const earthGeo = new THREE.SphereGeometry(1.05, 36, 36);
    const earthMat = new THREE.MeshStandardMaterial({
      map: createEarthTexture(),
      roughness: 0.35,
      metalness: 0.15
    });
    const earth = new THREE.Mesh(earthGeo, earthMat);
    scene.add(earth);

    // Aurora boundary rims (poles)
    const auroraGeo = new THREE.SphereGeometry(1.07, 32, 32);
    const auroraMat = new THREE.MeshBasicMaterial({
      color: 0x22c55e,
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending
    });
    const auroraRim = new THREE.Mesh(auroraGeo, auroraMat);
    scene.add(auroraRim);

    // Glowing atmosphere
    const atmosGeo = new THREE.SphereGeometry(1.09, 32, 32);
    const atmosMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.15,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide
    });
    const atmos = new THREE.Mesh(atmosGeo, atmosMat);
    scene.add(atmos);

    // ?? Volumetric Starfield ??
    const starCount = 180;
    const starGeo = new THREE.BufferGeometry();
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      const r = 18 + Math.random() * 12;
      starPositions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      starPositions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      starPositions[i * 3 + 2] = r * Math.cos(phi);
    }
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
    const starMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.08,
      transparent: true,
      opacity: 0.5,
      sizeAttenuation: true
    });
    const starfield = new THREE.Points(starGeo, starMat);
    scene.add(starfield);

    // ?? Physically-Traced Magnetic Field Lines ??
    // Model: an Earth-like dipole (moment aligned with +Y) superposed with a
    // uniform external field - a first-order (Mead/Dungey-style) model of
    // magnetospheric confinement:
    //   - a sunward "compression" term tied to the Shue standoff distance,
    //     which naturally compresses the dayside and stretches the tail
    //   - a "reconnection" term tied to southward IMF Bz, which genuinely
    //     opens polar-cap field lines when Bz goes strongly negative
    // Each line is produced by RK4 integration through this field (not
    // guessed/clamped point-by-point), so its curvature is a real
    // consequence of the field. Lines are rendered as tube geometry (a
    // bright core + a wider, dimmer glow layer) since WebGL line width is
    // unreliable across GPUs - this is what actually reads as "precise"
    // and dense rather than thin/aliased.
    const DIPOLE_MOMENT = 1.0;
    const fieldLineGroup = new THREE.Group();
    scene.add(fieldLineGroup);

    const dipoleFieldAt = (pos: THREE.Vector3, out: THREE.Vector3) => {
      const r2 = pos.lengthSq();
      if (r2 < 1e-6) { out.set(0, 0, 0); return out; }
      const r = Math.sqrt(r2);
      const mDotR = DIPOLE_MOMENT * pos.y; // moment vector = (0, M, 0)
      const c = (3 * mDotR) / (r2 * r2 * r);
      out.set(c * pos.x, c * pos.y - DIPOLE_MOMENT / (r2 * r), c * pos.z);
      return out;
    };

    const externalFieldVec = new THREE.Vector3();
    const totalFieldAt = (pos: THREE.Vector3, out: THREE.Vector3) => {
      dipoleFieldAt(pos, out);
      out.add(externalFieldVec);
      return out;
    };

    // RK4 integration of a single field line starting from a surface footpoint.
    // Reuses scratch vectors so tracing 100+ lines many times/sec doesn't churn the GC.
    const traceFieldLine = (start: THREE.Vector3, stepSize: number, maxSteps: number) => {
      const pts: THREE.Vector3[] = [start.clone()];
      const pos = start.clone();
      const k1 = new THREE.Vector3();
      const k2 = new THREE.Vector3();
      const k3 = new THREE.Vector3();
      const k4 = new THREE.Vector3();
      const tmp = new THREE.Vector3();

      for (let i = 0; i < maxSteps; i++) {
        totalFieldAt(pos, k1);
        let m = k1.length();
        if (m < 1e-8) break;
        k1.multiplyScalar(stepSize / m);

        tmp.copy(pos).addScaledVector(k1, 0.5);
        totalFieldAt(tmp, k2);
        m = k2.length();
        if (m < 1e-8) break;
        k2.multiplyScalar(stepSize / m);

        tmp.copy(pos).addScaledVector(k2, 0.5);
        totalFieldAt(tmp, k3);
        m = k3.length();
        if (m < 1e-8) break;
        k3.multiplyScalar(stepSize / m);

        tmp.copy(pos).add(k3);
        totalFieldAt(tmp, k4);
        m = k4.length();
        if (m < 1e-8) break;
        k4.multiplyScalar(stepSize / m);

        pos.x += (k1.x + 2 * k2.x + 2 * k3.x + k4.x) / 6;
        pos.y += (k1.y + 2 * k2.y + 2 * k3.y + k4.y) / 6;
        pos.z += (k1.z + 2 * k2.z + 2 * k3.z + k4.z) / 6;
        pts.push(pos.clone());

        const r = pos.length();
        if (r < 1.01) break; // re-entered the planet -> closed field line
        if (r > 40) break;   // escaped far downstream -> open field line
      }
      return pts;
    };

    // Seed footpoints on a colatitude/longitude grid. Dense enough to give
    // the woven, continuous look of a real field-line render. Tune these
    // two constants down if you need more headroom on lower-end GPUs.
    const FOOTPOINT_COLATS_DEG = [12, 20, 28, 37, 47, 58];
    const FOOTPOINTS_PER_RING = 20;
    const footpoints: THREE.Vector3[] = [];
    for (const deg of FOOTPOINT_COLATS_DEG) {
      const theta = THREE.MathUtils.degToRad(deg);
      for (let k = 0; k < FOOTPOINTS_PER_RING; k++) {
        const phi = (Math.PI * 2 * k) / FOOTPOINTS_PER_RING;
        footpoints.push(new THREE.Vector3(
          1.03 * Math.sin(theta) * Math.cos(phi),
          1.03 * Math.cos(theta),
          1.03 * Math.sin(theta) * Math.sin(phi)
        ));
      }
    }

    const rebuildFieldLines = (stormColor: THREE.Color, scaling: number, bz: number) => {
      while (fieldLineGroup.children.length) {
        const child = fieldLineGroup.children.pop() as THREE.Mesh;
        child.geometry.dispose();
        (child.material as THREE.Material).dispose();
      }

      const R_mp = 2.65 * scaling;
      const compression = 1.6 / Math.pow(R_mp, 3);
      const reconnection = bz < 0 ? Math.min(1.0, -bz / 18) * 0.55 : 0;
      externalFieldVec.set(compression, -reconnection, 0);

      for (const start of footpoints) {
        const pts = traceFieldLine(start, 0.09, 220);
        if (pts.length < 4) continue;
        const closed = pts[pts.length - 1].length() < 1.05;

        const curve = new THREE.CatmullRomCurve3(pts);
        const tubularSeg = Math.min(140, Math.max(24, pts.length));
        const coreRadius = closed ? 0.010 : 0.006;

        const coreGeo = new THREE.TubeGeometry(curve, tubularSeg, coreRadius, 5, false);
        const coreMat = new THREE.MeshBasicMaterial({
          color: stormColor,
          transparent: true,
          opacity: closed ? 0.6 : 0.24,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        });
        fieldLineGroup.add(new THREE.Mesh(coreGeo, coreMat));

        // Soft glow halo - fakes bloom without a postprocessing pass
        const glowGeo = new THREE.TubeGeometry(curve, Math.min(60, tubularSeg), coreRadius * 2.8, 5, false);
        const glowMat = new THREE.MeshBasicMaterial({
          color: stormColor,
          transparent: true,
          opacity: closed ? 0.14 : 0.06,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        });
        fieldLineGroup.add(new THREE.Mesh(glowGeo, glowMat));
      }
    };

    rebuildFieldLines(new THREE.Color(0x38bdf8), 0.9, 1.5); // initial build

    // ?? Laminar Flow IMF Lines Bending Around Bow Shock ??
    const swLineCount = 14;
    const swPointsCount = 42;
    const swLines: THREE.Line[] = [];
    const swGeometries: THREE.BufferGeometry[] = [];
    const swBaseY: number[] = [];
    const swBaseZ: number[] = [];

    for (let i = 0; i < swLineCount; i++) {
      const y_init = -5.5 + 11.0 * (i / (swLineCount - 1));
      const z_init = -1.2 + Math.random() * 2.4;
      swBaseY.push(y_init);
      swBaseZ.push(z_init);

      const swGeo = new THREE.BufferGeometry();
      const swPos = new Float32Array(swPointsCount * 3);
      swGeo.setAttribute("position", new THREE.BufferAttribute(swPos, 3));
      swGeometries.push(swGeo);

      const swMat = new THREE.LineBasicMaterial({
        color: 0xfbbf24,
        transparent: true,
        opacity: 0.42,
        blending: THREE.AdditiveBlending
      });
      const swLine = new THREE.Line(swGeo, swMat);
      scene.add(swLine);
      swLines.push(swLine);
    }

    // ?? Glowing Parabolic Bow Shock Wave ??
    const shockPointsCount = 50;
    const shockGeo = new THREE.BufferGeometry();
    const shockPos = new Float32Array(shockPointsCount * 3);
    shockGeo.setAttribute("position", new THREE.BufferAttribute(shockPos, 3));
    
    const shockMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending
    });
    const shockLine = new THREE.Line(shockGeo, shockMat);
    scene.add(shockLine);

    // ?? Animated Solar Wind Particles ??
    const windPartCount = 40;
    const windGeo = new THREE.BufferGeometry();
    const windPositions = new Float32Array(windPartCount * 3);
    const windY: number[] = [];
    const windZ: number[] = [];
    const windOffset: number[] = [];
    
    for (let i = 0; i < windPartCount; i++) {
      windPositions[i * 3] = -9.0 + Math.random() * 18.0;
      const y = -4.5 + Math.random() * 9.0;
      const z = -1.5 + Math.random() * 3.0;
      
      windPositions[i * 3 + 1] = y;
      windPositions[i * 3 + 2] = z;
      windY.push(y);
      windZ.push(z);
      windOffset.push(1.0 + Math.random() * 0.3);
    }
    
    windGeo.setAttribute("position", new THREE.BufferAttribute(windPositions, 3));
    const windParticleMat = new THREE.PointsMaterial({
      color: 0xfbbf24,
      size: 0.08,
      transparent: true,
      opacity: 0.65,
      sizeAttenuation: true
    });
    const windParticles = new THREE.Points(windGeo, windParticleMat);
    scene.add(windParticles);

    // ?? Animation Loop ??
    let raf: number;
    let clock = new THREE.Clock();
    let fieldLineTimer = 0; // throttles the RK4 retrace + tube rebuild

    const getStormColor = (intensity: number) => {
      if (intensity < 0.35) return new THREE.Color(0x38bdf8); // calm blue
      if (intensity < 0.7) return new THREE.Color(0xfbbf24);  // flare gold
      return new THREE.Color(0xef4444);                      // carrington red
    };

    const animate = () => {
      raf = requestAnimationFrame(animate);
      
      const time = clock.getElapsedTime();
      const p = physicsRef.current;
      
      const intensity = p.intensity;
      const scaling = p.scaling_factor;
      const speed = p.wind_speed;
      const bz = p.bz;

      // 1. Earth rotation
      earth.rotation.y = time * 0.022;

      // 2. Atmosphere & Auroral rim glows
      const stormColor = getStormColor(intensity);
      atmosMat.color.copy(stormColor);
      atmosMat.opacity = 0.12 + 0.16 * intensity;
      
      // Auroras flare up at poles during negative Bz storms
      auroraMat.color.copy(stormColor);
      auroraMat.opacity = bz < 0 ? 0.15 + 0.28 * Math.min(1.0, -bz / 15.0) : 0.08;

      // 3. Compute Shue et al. (1998) boundary limits (used by bow shock & IMF lines below)
      const R_mp = 2.65 * scaling;
      const alpha = 0.52 + 0.14 * (1.0 - scaling);

      // 4. Retrace magnetic field lines (throttled - RK4 + tube rebuild is
      // far more expensive than the cheap per-frame updates around it, but
      // ~8-9 times/sec is still plenty responsive to live data changes)
      fieldLineTimer += 1;
      if (fieldLineTimer >= 7) {
        fieldLineTimer = 0;
        rebuildFieldLines(stormColor, scaling, bz);
      }

      // 5. Update Bow Shock Parabola (Shue-based standalone wave front)
      const shockPosAttr = shockGeo.attributes.position;
      const shockArray = shockPosAttr.array as Float32Array;
      
      shockMat.color.copy(stormColor);
      shockMat.opacity = 0.45 + 0.45 * intensity;
      const shockFlex = 0.06 * Math.sin(time * 8.5);

      for (let i = 0; i < shockPointsCount; i++) {
        const y = -4.5 + 9.0 * (i / (shockPointsCount - 1));
        
        // Parabolic bow shock standoff distance: x = -R_mp * 1.15
        const R_shock = R_mp * 1.14;
        const curvature = 0.165 / (scaling * 0.9);
        const x = -R_shock - curvature * Math.pow(y, 2) + shockFlex * Math.exp(-Math.pow(y, 2) / 4.0);
        
        shockArray[i * 3] = x;
        shockArray[i * 3 + 1] = y;
        shockArray[i * 3 + 2] = 0.0;
      }
      shockPosAttr.needsUpdate = true;

      // 6. Update IMF Solar Wind Lines (Bending around Shue boundary)
      for (let l = 0; l < swLines.length; l++) {
        const line = swLines[l];
        const geo = swGeometries[l];
        const posAttr = geo.attributes.position;
        const posArray = posAttr.array as Float32Array;
        const y_init = swBaseY[l];
        const z_init = swBaseZ[l];
        
        const lineMat = line.material as THREE.LineBasicMaterial;
        if (bz < -8.0) {
          lineMat.color.setHex(0xef4444); // red for negative Bz reconnection
        } else if (bz < -2.0) {
          lineMat.color.setHex(0xfbbf24); // gold/orange
        } else {
          lineMat.color.setHex(0x38bdf8); // calm blue IMF
        }
        lineMat.opacity = 0.28 + 0.28 * intensity;

        for (let i = 0; i < swPointsCount; i++) {
          const x = -9.0 + 18.0 * (i / (swPointsCount - 1));
          let y = y_init;
          let z = z_init;
          
          // Deflect smoothly around the bow shock nose
          if (x > -R_mp * 1.6 && x < 4.0) {
            const centerDist = -R_mp * 1.12;
            const deflectAmp = 2.5 * Math.exp(-Math.pow(x - centerDist, 2) / 6.0);
            if (Math.abs(y_init) < 4.5) {
              const sign = y_init >= 0 ? 1.0 : -1.0;
              y = y_init + sign * deflectAmp * (1.0 - Math.abs(y_init) / 4.5);
            }
          }
          
          // Tiny high-frequency waves
          y += 0.02 * Math.sin(time * 9.5 + x * 2.2);

          posArray[i * 3] = x;
          posArray[i * 3 + 1] = y;
          posArray[i * 3 + 2] = z;
        }
        posAttr.needsUpdate = true;
      }

      // 7. Flow particles dynamically proportional to speed
      const windPosAttr = windGeo.attributes.position;
      const windArray = windPosAttr.array as Float32Array;
      const pSpeed = 0.03 + 0.12 * (speed / 400.0);
      
      windParticleMat.color.copy(stormColor);
      windParticleMat.size = 0.07 + 0.065 * intensity;

      for (let i = 0; i < windPartCount; i++) {
        let x = windArray[i * 3] + pSpeed;
        let y = windY[i];
        let z = windZ[i];
        const offset = windOffset[i];
        
        if (x > 9.0) {
          x = -9.0;
          y = -4.5 + Math.random() * 9.0;
          z = -1.5 + Math.random() * 3.0;
          windY[i] = y;
          windZ[i] = z;
        }
        
        const curvature = 0.165 / (scaling * 0.9);
        const shockX = -R_mp * 1.14 - curvature * Math.pow(y, 2);
        
        if (x > shockX) {
          const distToShock = x - shockX;
          if (distToShock < 3.0) {
            const radBoundary = Math.sqrt(Math.max(0.1, (R_mp * 1.14 + x) / curvature));
            const targetY = radBoundary * offset * (y >= 0 ? 1 : -1);
            y = targetY;
          }
        }

        windArray[i * 3] = x;
        windArray[i * 3 + 1] = y;
        windArray[i * 3 + 2] = z;
      }
      windPosAttr.needsUpdate = true;

      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", handleResize);
      container.removeChild(renderer.domElement);
      
      earthGeo.dispose();
      earthMat.dispose();
      atmosGeo.dispose();
      atmosMat.dispose();
      auroraGeo.dispose();
      auroraMat.dispose();
      starGeo.dispose();
      starMat.dispose();
      shockGeo.dispose();
      shockMat.dispose();
      windGeo.dispose();
      windParticleMat.dispose();
      
      while (fieldLineGroup.children.length) {
        const child = fieldLineGroup.children.pop() as THREE.Mesh;
        child.geometry.dispose();
        (child.material as THREE.Material).dispose();
      }
      scene.remove(fieldLineGroup);

      swGeometries.forEach(g => g.dispose());
      swLines.forEach(l => {
        const m = l.material as THREE.Material;
        m.dispose();
      });
    };
  }, []);

  // Backlighting color maps
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
    if (intensity < 0.35) return "border-[#0ea5e9]/10";
    if (intensity < 0.7) return "border-[#fbbf24]/30";
    return "border-[#ef4444]/55 animate-pulse";
  };

  return (
    <div
      className={`relative w-full h-full flex flex-col overflow-hidden rounded-2xl border transition-all duration-700 ${getBorderColor()}`}
      style={{
        background: "#050810",
        boxShadow: "0 4px 30px rgba(0, 0, 0, 0.4)"
      }}
    >
      <div 
        className="absolute inset-0 pointer-events-none transition-all duration-700" 
        style={{ background: getAmbientBacklight() }}
      />

      {/* WebGL Canvas Container */}
      <div ref={containerRef} className="flex-1 w-full h-full min-h-0 relative z-0" />

      {/* Header Overlay HUD Panel */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-start pointer-events-none z-10">
        <div className="flex flex-col gap-1">
          <span className="text-[9px] font-mono text-white/30 tracking-widest uppercase font-bold">
            NOAA Space Weather Simulation
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
      <div className="absolute top-16 left-4 flex flex-col gap-2 pointer-events-none z-10 font-mono text-[9px] text-white/45 bg-black/35 p-2.5 rounded-lg border border-white/5 backdrop-blur-sm">
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
          <span className="font-bold text-sky-400">{data.scaling_factor.toFixed(2)} R_E</span>
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
      <div className="absolute bottom-4 left-4 right-4 bg-black/45 border border-white/5 p-3 rounded-xl flex items-center justify-between gap-6 z-10 pointer-events-auto backdrop-blur-md">
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
            className="flex-1 h-1 bg-white/15 rounded-lg appearance-none cursor-pointer accent-[#4a90a4] focus:outline-none"
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