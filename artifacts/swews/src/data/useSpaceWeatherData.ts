import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchJson, API_BASE, WS_BASE } from "@/lib/api";

/* ── Types ─────────────────────────────────────────────────────────────── */

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

export interface ChartPoint {
  time: string;
  electron800kev: number;
  electron2mev: number;
}

export interface StormProbability {
  probability: number;
  confidence: number;
  label: string;
  reasons: { label: string; value: string }[];
}

export interface RegressionIntensity {
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

export interface GOESElectronPoint {
  timestamp: string;
  electron_flux_800kev: number;
  electron_flux_2mev: number;
}

export interface GOESProtonPoint {
  timestamp: string;
  flux: number;
  energy?: string;
}

export interface GOESPayload {
  electrons: GOESElectronPoint[];
  protons: GOESProtonPoint[];
  url_electrons: string;
  url_protons: string;
  source: string;
}

export interface DSCOVRPlasmaPoint {
  timestamp: string;
  dscovr_density: number;
  dscovr_speed: number;
  dscovr_temperature: number;
}

export interface DSCOVRMagPoint {
  timestamp: string;
  dscovr_bx: number;
  dscovr_by: number;
  dscovr_bz: number;
  dscovr_bt: number;
  bz_gsm?: number;
}

export interface DSCOVRPayload {
  plasma: DSCOVRPlasmaPoint[];
  mag: DSCOVRMagPoint[];
  url_plasma: string;
  url_mag: string;
  source: string;
}

/* ── Helpers ──────────────────────────────────────────────────────────── */

const scientific = (value: number) => value.toExponential(2).replace("e+", "e");
const parseScientificValue = (value: string) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};
const timeAgo = (timestamp: string) => {
  const deltaMs = Date.now() - new Date(timestamp).getTime();
  const deltaMin = Math.max(0, Math.round(deltaMs / 60000));
  if (deltaMin < 1) return "Just now";
  if (deltaMin === 1) return "1m ago";
  return `${deltaMin}m ago`;
};
const getTrend = (current: number, previous: number): "up" | "down" | "flat" => {
  if (!Number.isFinite(previous) || current === previous) return "flat";
  return current > previous ? "up" : "down";
};

/* ── Query keys ───────────────────────────────────────────────────────── */

export const queryKeys = {
  intensity: ["intensity"] as const,
  goes: ["live", "goes"] as const,
  dscovr: ["live", "dscovr"] as const,
};

/* ── Polling intervals (single source of truth) ──────────────────────── */

export const REFRESH = {
  intensityMs: 5_000,    // backend caches for 30s, but we re-poll fast so UI feels live
  goesMs: 30_000,
  dscovrMs: 30_000,
} as const;

/* ── Hooks ────────────────────────────────────────────────────────────── */

export function useIntensity() {
  return useQuery({
    queryKey: queryKeys.intensity,
    queryFn: () => fetchJson<RegressionIntensity>("/api/regression-intensity"),
    refetchInterval: REFRESH.intensityMs,
    placeholderData: keepPreviousData,
    staleTime: REFRESH.intensityMs / 2,
  });
}

export function useGoesLive() {
  return useQuery({
    queryKey: queryKeys.goes,
    queryFn: () => fetchJson<GOESPayload>("/api/live/goes"),
    refetchInterval: REFRESH.goesMs,
    placeholderData: keepPreviousData,
    staleTime: REFRESH.goesMs / 2,
  });
}

export function useDscovrLive() {
  return useQuery({
    queryKey: queryKeys.dscovr,
    queryFn: () => fetchJson<DSCOVRPayload>("/api/live/dscovr"),
    refetchInterval: REFRESH.dscovrMs,
    placeholderData: keepPreviousData,
    staleTime: REFRESH.dscovrMs / 2,
  });
}

/* ── Derived data: telemetry, alerts, chartData, stormProbability ─────── */

const TELEMETRY_TEMPLATE: Telemetry[] = [
  { id: "1", name: "Electron Flux", value: "0.00e0", trend: "flat", status: "nominal", unit: "pfu" },
  { id: "2", name: "Proton Flux", value: "0.00e0", trend: "flat", status: "nominal", unit: "pfu" },
  { id: "3", name: "Solar Wind Speed", value: "0.0", trend: "flat", status: "nominal", unit: "km/s" },
  { id: "4", name: "IMF Bz", value: "0.0", trend: "flat", status: "nominal", unit: "nT" },
  { id: "5", name: "Kp Index", value: "0.0", trend: "flat", status: "nominal", unit: "" },
  { id: "6", name: "Dst Index", value: "0", trend: "flat", status: "nominal", unit: "nT" },
  { id: "7", name: "AE Index", value: "0", trend: "flat", status: "nominal", unit: "nT" },
  { id: "8", name: "X-ray Proxy", value: "B1.0", trend: "flat", status: "nominal", unit: "class" },
];

/**
 * Builds a live Telemetry[] snapshot from intensity + GOES feeds.
 * Pure derivation — no fetching. Backed by useIntensity() and useGoesLive().
 */
export function useLiveTelemetry(): Telemetry[] {
  const intensity = useIntensity().data;
  const goes = useGoesLive().data;

  if (!intensity) return TELEMETRY_TEMPLATE;

  const latestElectron = goes?.electrons?.at(-1)?.electron_flux_2mev ?? 0;
  const latestProton = goes?.protons?.at(-1)?.flux ?? 0;

  return TELEMETRY_TEMPLATE.map((item) => {
    if (item.name === "Solar Wind Speed") {
      return {
        ...item,
        value: intensity.wind_speed.toFixed(1),
        trend: getTrend(intensity.wind_speed, Number(item.value)),
        status: intensity.wind_speed > 700 ? "critical" : intensity.wind_speed > 550 ? "elevated" : "nominal",
      };
    }
    if (item.name === "IMF Bz") {
      return {
        ...item,
        value: intensity.bz.toFixed(1),
        trend: getTrend(intensity.bz, Number(item.value)),
        status: intensity.bz < -8 ? "critical" : intensity.bz < -4 ? "elevated" : "nominal",
      };
    }
    if (item.name === "Electron Flux") {
      return {
        ...item,
        value: scientific(latestElectron),
        trend: getTrend(latestElectron, parseScientificValue(item.value)),
        status: latestElectron > 1e4 ? "critical" : latestElectron > 1e3 ? "elevated" : "nominal",
      };
    }
    if (item.name === "Proton Flux") {
      return {
        ...item,
        value: scientific(latestProton),
        trend: getTrend(latestProton, parseScientificValue(item.value)),
        status: latestProton > 1e2 ? "critical" : latestProton > 1e1 ? "elevated" : "nominal",
      };
    }
    if (item.name === "Kp Index") {
      const kp = Math.max(0, Math.min(9, 1.4 + intensity.intensity * 7.2));
      return {
        ...item,
        value: kp.toFixed(1),
        trend: getTrend(kp, Number(item.value)),
        status: kp > 6 ? "critical" : kp > 4 ? "elevated" : "nominal",
      };
    }
    if (item.name === "Dst Index") {
      const dst = Math.round(-(10 + intensity.intensity * 130));
      return {
        ...item,
        value: dst.toString(),
        trend: getTrend(dst, Number(item.value)),
        status: dst < -100 ? "critical" : dst < -30 ? "elevated" : "nominal",
      };
    }
    if (item.name === "AE Index") {
      const ae = Math.round(120 + intensity.intensity * 900);
      return {
        ...item,
        value: ae.toString(),
        trend: getTrend(ae, Number(item.value)),
        status: ae > 800 ? "critical" : ae > 400 ? "elevated" : "nominal",
      };
    }
    if (item.name === "X-ray Proxy") {
      const flareClass = intensity.intensity > 0.75 ? "X2.8" : intensity.intensity > 0.45 ? "M3.1" : "B2.5";
      return {
        ...item,
        value: flareClass,
        status: intensity.intensity > 0.75 ? "critical" : intensity.intensity > 0.45 ? "elevated" : "nominal",
      };
    }
    return item;
  });
}

const ALERT_BOOT: Alert[] = [
  { id: "boot", severity: "INFO", title: "Telemetry initialization in progress", time: "Just now" },
];

export function useLiveAlerts(): { alerts: Alert[]; dismissAlert: (id: string) => void } {
  const intensity = useIntensity().data;
  const goes = useGoesLive().data;
  const [dismissed, setDismissed] = useState<string[]>([]);

  const dismissAlert = (id: string) => setDismissed((prev) => [...prev, id]);

  const alerts: Alert[] = [];
  if (intensity) {
    const latestElectron = goes?.electrons?.at(-1)?.electron_flux_2mev ?? 0;
    const latestTime = goes?.electrons?.at(-1)?.timestamp ?? new Date().toISOString();

    if (intensity.bz < -10 || intensity.wind_speed > 750) {
      alerts.push({
        id: "storm-driver",
        severity: "CRITICAL",
        title: `Storm driver active: Bz ${intensity.bz.toFixed(1)} nT, wind ${intensity.wind_speed.toFixed(0)} km/s`,
        time: "Just now",
      });
    }
    if (latestElectron > 10000) {
      alerts.push({
        id: "electron-severe",
        severity: "CRITICAL",
        title: `GOES >2 MeV electron flux severe: ${scientific(latestElectron)} pfu`,
        time: timeAgo(latestTime),
      });
    } else if (latestElectron > 1000) {
      alerts.push({
        id: "electron-elevated",
        severity: "WARNING",
        title: `GOES >2 MeV electron flux elevated: ${scientific(latestElectron)} pfu`,
        time: timeAgo(latestTime),
      });
    }
    alerts.push({
      id: "telemetry-link",
      severity: intensity.live ? "INFO" : "WARNING",
      title: intensity.live ? "NOAA telemetry feed healthy" : "Fallback telemetry model active",
      time: "Just now",
    });
  } else {
    alerts.push(...ALERT_BOOT);
  }

  return {
    alerts: alerts.filter((a) => !dismissed.includes(a.id)),
    dismissAlert,
  };
}

export function useLiveChartData(): ChartPoint[] {
  const goes = useGoesLive().data;
  if (!goes?.electrons) return [];
  return goes.electrons.slice(-24).map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    electron800kev: point.electron_flux_800kev ?? 0,
    electron2mev: point.electron_flux_2mev ?? 0,
  }));
}

const STORM_DEFAULT: StormProbability = {
  probability: 0,
  confidence: 80,
  label: "Safe",
  reasons: [
    { label: "IMF Bz", value: "0%" },
    { label: "Solar wind speed", value: "0%" },
    { label: "GOES electron flux", value: "0%" },
    { label: "Dynamic pressure", value: "0%" },
  ],
};

export function useStormProbability(): StormProbability {
  const intensity = useIntensity().data;
  const goes = useGoesLive().data;
  if (!intensity) return STORM_DEFAULT;

  const latestElectron = goes?.electrons?.at(-1)?.electron_flux_2mev ?? 0;
  const electronScore = Math.min(20, (latestElectron / 10000) * 20);
  const bzScore = Math.min(30, Math.max(0, -intensity.bz) * 2.3);
  const speedScore = Math.min(25, Math.max(0, intensity.wind_speed - 400) / 14);
  const pressureScore = Math.min(15, intensity.dynamic_pressure * 1.15);
  const probability = Math.round(
    Math.min(99, Math.max(5, intensity.intensity * 18 + electronScore + bzScore + speedScore + pressureScore))
  );
  const confidence = Math.round(Math.max(72, Math.min(99, 80 + intensity.intensity * 18)));
  const label =
    probability >= 85 ? "Critical" :
    probability >= 65 ? "Severe" :
    probability >= 45 ? "Moderate" :
    probability >= 25 ? "Minor" : "Safe";

  return {
    probability,
    confidence,
    label,
    reasons: [
      { label: `IMF Bz ${intensity.bz.toFixed(1)} nT`, value: `${Math.round(bzScore)}%` },
      { label: `Solar Wind ${intensity.wind_speed.toFixed(0)} km/s`, value: `${Math.round(speedScore)}%` },
      { label: `GOES >2 MeV ${latestElectron.toExponential(1)} pfu`, value: `${Math.round(electronScore)}%` },
      { label: `Pressure ${intensity.dynamic_pressure.toFixed(1)} nPa`, value: `${Math.round(pressureScore)}%` },
    ],
  };
}

/* ── Re-exports ───────────────────────────────────────────────────────── */
export { API_BASE, WS_BASE };
