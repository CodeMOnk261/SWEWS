import { useLiveTelemetry } from "@/data/liveData";
import { ArrowUpRight, ArrowDownRight, ArrowRight } from "lucide-react";

const statusDot: Record<string, string> = {
  nominal: "rgba(61,139,55,0.9)",
  elevated: "rgba(212,168,67,0.9)",
  critical: "rgba(163,48,48,0.9)",
};

export function LiveTelemetry() {
  const telemetry = useLiveTelemetry();

  return (
    <div className="flex flex-col gap-2 h-full min-h-0">
      <h3 className="text-[10px] font-semibold text-white/35 uppercase tracking-widest px-1">Live Telemetry</h3>
      <div
        className="flex-1 overflow-y-auto rounded-2xl min-h-0"
        style={{
          background: "linear-gradient(160deg, #111520 0%, #0d1117 100%)",
          border: "1px solid #1e2230",
        }}
      >
        <div className="divide-y divide-white/5">
          {telemetry.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between px-3 py-2.5 hover:bg-white/3 transition-colors"
              data-testid={`telemetry-${t.id}`}
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: statusDot[t.status], boxShadow: `0 0 5px ${statusDot[t.status]}` }}
                />
                <span className="text-xs text-white/55 truncate">{t.name}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono text-xs text-white/80">{t.value}</span>
                {t.unit && <span className="text-[10px] text-white/25 font-mono">{t.unit}</span>}
                {t.trend === "up"   && <ArrowUpRight   size={11} className="text-amber-400/70" />}
                {t.trend === "down" && <ArrowDownRight  size={11} className="text-sky-400/70" />}
                {t.trend === "flat" && <ArrowRight      size={11} className="text-white/25" />}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
