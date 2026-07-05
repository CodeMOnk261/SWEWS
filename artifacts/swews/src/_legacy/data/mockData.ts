import { useState, useEffect } from "react";

export interface Alert {
  id: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  title: string;
  time: string;
}

export interface Telemetry {
  id: string;
  name: string;
  value: string;
  trend: "up" | "down" | "flat";
  status: "nominal" | "elevated" | "critical";
  unit: string;
}

export function useMockAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([
    { id: "1", severity: "CRITICAL", title: "CME Detected — Solar Wind +340 km/s", time: "Just now" },
    { id: "2", severity: "WARNING", title: "Kp Index Elevated: 6.2", time: "2m ago" },
    { id: "3", severity: "INFO", title: "GOES-16 Stream Nominal", time: "15m ago" },
  ]);

  const dismissAlert = (id: string) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
  };

  return { alerts, dismissAlert };
}

export function useMockTelemetry() {
  const [telemetry, setTelemetry] = useState<Telemetry[]>([
    { id: "1", name: "Electron Flux", value: "2.45e3", trend: "up", status: "elevated", unit: "pfu" },
    { id: "2", name: "Proton Flux", value: "1.02e1", trend: "flat", status: "nominal", unit: "pfu" },
    { id: "3", name: "Solar Wind Speed", value: "482.5", trend: "up", status: "nominal", unit: "km/s" },
    { id: "4", name: "IMF Bz", value: "-4.2", trend: "down", status: "elevated", unit: "nT" },
    { id: "5", name: "Kp Index", value: "4.3", trend: "up", status: "elevated", unit: "" },
    { id: "6", name: "Dst Index", value: "-25", trend: "down", status: "nominal", unit: "nT" },
    { id: "7", name: "AE Index", value: "450", trend: "up", status: "nominal", unit: "nT" },
    { id: "8", name: "X-ray Flux", value: "B2.5", trend: "flat", status: "nominal", unit: "W/m²" },
  ]);

  useEffect(() => {
    let active = true;

    const fetchData = async () => {
      try {
        const resReg = await fetch("http://localhost:8000/api/regression-intensity");
        if (!resReg.ok) return;
        const reg = await resReg.json();

        const resGoes = await fetch("http://localhost:8000/api/live/goes");
        let goesElectrons = null;
        let goesProtons = null;
        if (resGoes.ok) {
          const goes = await resGoes.json();
          goesElectrons = goes.electrons;
          goesProtons = goes.protons;
        }

        if (!active) return;

        setTelemetry(prev => prev.map(t => {
          if (t.name === "Solar Wind Speed") {
            const val = reg.wind_speed;
            const prevVal = parseFloat(t.value);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val > 700 ? "critical" : val > 550 ? "elevated" : "nominal";
            return { ...t, value: val.toFixed(1), trend, status };
          }
          if (t.name === "IMF Bz") {
            const val = reg.bz;
            const prevVal = parseFloat(t.value);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val < -8.0 ? "critical" : val < -4.0 ? "elevated" : "nominal";
            return { ...t, value: val.toFixed(1), trend, status };
          }
          if (t.name === "Electron Flux" && goesElectrons && goesElectrons.length > 0) {
            const latest = goesElectrons[goesElectrons.length - 1];
            const val = latest.electron_flux_2mev || 2.45e3;
            const prevVal = parseFloat(t.value.split("e")[0]) * Math.pow(10, parseInt(t.value.split("e")[1]) || 0);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val > 1e4 ? "critical" : val > 1e3 ? "elevated" : "nominal";
            let formatted = val.toExponential(2).replace("e+", "e");
            return { ...t, value: formatted, trend, status };
          }
          if (t.name === "Proton Flux" && goesProtons && goesProtons.length > 0) {
            const latest = goesProtons[goesProtons.length - 1];
            const val = latest.flux || 1.02e1;
            const prevVal = parseFloat(t.value.split("e")[0]) * Math.pow(10, parseInt(t.value.split("e")[1]) || 0);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val > 1e2 ? "critical" : val > 1e1 ? "elevated" : "nominal";
            let formatted = val.toExponential(2).replace("e+", "e");
            return { ...t, value: formatted, trend, status };
          }
          if (t.name === "Kp Index") {
            const baseKp = reg.bz < -12.0 ? 7.5 : reg.bz < -4.0 ? 5.2 : 2.5;
            const val = baseKp + (Math.random() * 0.4 - 0.2);
            const prevVal = parseFloat(t.value);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val > 6.0 ? "critical" : val > 4.0 ? "elevated" : "nominal";
            return { ...t, value: Math.max(0, Math.min(9, val)).toFixed(1), trend, status };
          }
          if (t.name === "Dst Index") {
            const baseDst = reg.bz < -12.0 ? -120 : reg.bz < -4.0 ? -45 : -15;
            const val = Math.round(baseDst + (Math.random() * 6 - 3));
            const prevVal = parseInt(t.value);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val < -100 ? "critical" : val < -30 ? "elevated" : "nominal";
            return { ...t, value: val.toString(), trend, status };
          }
          if (t.name === "AE Index") {
            const baseAE = reg.bz < -12.0 ? 950 : reg.bz < -4.0 ? 450 : 150;
            const val = Math.round(baseAE + (Math.random() * 40 - 20));
            const prevVal = parseInt(t.value);
            const trend = val > prevVal ? "up" : val < prevVal ? "down" : "flat";
            const status = val > 800 ? "critical" : val > 400 ? "elevated" : "nominal";
            return { ...t, value: val.toString(), trend, status };
          }
          if (t.name === "X-ray Flux") {
            const intensity = reg.intensity;
            const flareClass = intensity > 0.7 ? "X3.2" : intensity > 0.4 ? "M1.5" : "B2.5";
            return { ...t, value: flareClass, status: intensity > 0.7 ? "critical" : intensity > 0.4 ? "elevated" : "nominal" };
          }
          return t;
        }));
      } catch (err) {
        console.error("Error fetching live telemetry:", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 4000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return telemetry;
}

export function useMockChartData() {
  const [data, setData] = useState<{ time: string; historical: number; current: number }[]>([]);

  useEffect(() => {
    const base = Array.from({ length: 24 }).map((_, i) => {
      const time = new Date(Date.now() - (24 - i) * 60000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return {
        time,
        historical: 1000 + Math.random() * 500,
        current: 1200 + Math.random() * 800 + (i > 15 ? i * 50 : 0)
      };
    });
    setData(base);

    const interval = setInterval(() => {
      setData(prev => {
        const next = [...prev.slice(1)];
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        next.push({
          time,
          historical: 1000 + Math.random() * 500,
          current: 2000 + Math.random() * 1000
        });
        return next;
      });
    }, 60000);

    return () => clearInterval(interval);
  }, []);

  return data;
}
