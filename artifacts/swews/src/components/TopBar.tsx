import { useState, useEffect } from "react";

export function TopBar() {
  const [time, setTime] = useState("");

  useEffect(() => {
    const update = () => {
      setTime(new Date().toISOString().substring(11, 19) + " UTC");
    };
    update();
    const int = setInterval(update, 1000);
    return () => clearInterval(int);
  }, []);

  return (
    <header
      className="h-[48px] flex items-center justify-between px-5 shrink-0"
      style={{
        background: "linear-gradient(90deg, #131720 0%, #0f1419 100%)",
        borderBottom: "1px solid #1e2230",
      }}
    >
      <div className="flex items-center gap-3 w-1/3">
        <span className="font-bold text-sm tracking-widest text-white/80 font-mono">SWEWS</span>
      </div>

      <div className="flex items-center justify-center gap-2.5 w-1/3">
        <div
          className="flex items-center gap-2 px-3 py-1 rounded-full text-xs"
          style={{
            background: "linear-gradient(90deg, rgba(61,139,55,0.12), rgba(74,144,164,0.08))",
            border: "1px solid rgba(61,139,55,0.2)",
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          <span className="text-white/70 font-medium">NOAA GOES-16/18</span>
          <span className="text-white/35 font-mono text-[10px]">LIVE</span>
        </div>
      </div>

      <div className="flex items-center justify-end gap-3 w-1/3">
        <span className="font-mono text-xs text-white/50">{time}</span>
        <div
          className="text-[10px] font-mono px-2 py-0.5 rounded-md text-white/40"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}
        >
          v2.4.1
        </div>
        <div
          className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white/60"
          style={{ background: "linear-gradient(135deg, #2a3040, #1e2530)", border: "1px solid rgba(255,255,255,0.1)" }}
        >
          JD
        </div>
      </div>
    </header>
  );
}
