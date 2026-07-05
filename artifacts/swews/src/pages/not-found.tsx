import { Link } from "wouter";
import { Activity, AlertCircle, ChevronRight, Globe2 } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-[#0f111a] text-foreground overflow-hidden">
      <div
        className="relative w-full max-w-md mx-4 rounded-3xl border border-white/8 p-8"
        style={{
          background: "linear-gradient(160deg, #111520 0%, #0d1117 100%)",
          boxShadow: "0 30px 80px rgba(0,0,0,0.42)",
        }}
      >
        <div className="absolute inset-x-5 top-5 z-0 opacity-30">
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Solar wind", value: "—", color: "text-white/30" },
              { label: "IMF Bz", value: "—", color: "text-white/30" },
              { label: "Risk state", value: "Unknown", color: "text-white/30" },
              { label: "Telemetry", value: "Offline", color: "text-rose-400/60" },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-white/6 bg-[#08111c]/40 p-2.5"
              >
                <div className="text-[9px] font-mono uppercase tracking-widest text-white/25">
                  {s.label}
                </div>
                <div className={`text-sm font-semibold ${s.color}`}>{s.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 pt-44 flex flex-col gap-5">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-white/35">
            <Globe2 size={12} />
            Magnetosphere
          </div>
          <div className="flex items-center gap-2 text-white/80">
            <AlertCircle className="h-6 w-6 text-rose-400" />
            <h1 className="text-2xl font-bold tracking-tight">404 — Page not found</h1>
          </div>
          <p className="text-sm text-white/45 leading-relaxed">
            The route you requested does not exist on the SWEWS console. The
            magnetosphere model has no telemetry for this coordinate.
          </p>
          <div className="flex items-center gap-3 pt-2">
            <Link
              href="/dashboard"
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold border border-white/10 hover:border-white/20 text-white/80 hover:text-white transition-all"
              data-testid="notfound-dashboard"
            >
              <Activity size={13} />
              Open Mission Control
              <ChevronRight size={13} />
            </Link>
            <Link
              href="/live"
              className="text-xs text-white/45 hover:text-white/70 transition-colors"
              data-testid="notfound-live"
            >
              Live Weather →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
