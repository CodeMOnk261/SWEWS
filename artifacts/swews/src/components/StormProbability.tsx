import { ChevronDown } from "lucide-react";
import { useStormProbability } from "@/data/liveData";

const labels = ["Safe", "Minor", "Moderate", "Severe", "Critical"];

export function StormProbability() {
  const { probability, confidence, label, reasons } = useStormProbability();

  return (
    <div
      className="rounded-2xl p-4 flex flex-col gap-3"
      style={{
        background: "linear-gradient(160deg, #131820 0%, #0d1117 100%)",
        border: "1px solid #1e2230",
      }}
      >
        <div className="flex items-center justify-between">
        <h3 className="text-[10px] font-semibold text-white/35 uppercase tracking-widest">Storm Probability</h3>
        <span className="font-mono text-[10px] text-white/25">CONF {confidence}%</span>
      </div>

      <div className="flex items-end justify-between">
        <span
          className="text-3xl font-bold font-mono leading-none"
          style={{ background: "linear-gradient(135deg, #d4a843, #e8c060)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}
        >
          {probability}%
        </span>
        <span
          className="text-xs font-semibold tracking-wide uppercase"
          style={{ color: "#c89a30" }}
        >
          {label}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-full rounded-full transition-all duration-1000"
          style={{
            width: `${probability}%`,
            background: "linear-gradient(90deg, #4a90a4 0%, #d4a843 60%, #c94040 100%)",
            backgroundSize: "200% 100%",
            backgroundPosition: `${probability}% center`,
          }}
        />
      </div>

      {/* Tick marks */}
      <div className="flex justify-between text-[9px] font-mono text-white/20 -mt-1.5">
        {labels.map((l) => <span key={l}>{l}</span>)}
      </div>

      <details className="group cursor-pointer mt-1">
        <summary className="flex items-center gap-1.5 text-[10px] font-medium text-white/30 hover:text-white/50 list-none transition-colors">
          AI Reasoning
          <ChevronDown size={10} className="group-open:rotate-180 transition-transform" />
        </summary>
        <div className="mt-3 space-y-2 text-[10px] font-mono text-white/40 pl-3 border-l border-white/8">
          {reasons.map((reason) => (
            <div key={reason.label} className="flex justify-between">
              <span>{reason.label}</span>
              <span style={{ color: "#c89a30" }}>+{reason.value}</span>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
