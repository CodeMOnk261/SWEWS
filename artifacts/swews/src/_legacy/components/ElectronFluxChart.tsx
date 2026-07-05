import { ResponsiveContainer, ReferenceLine, Tooltip, Area, AreaChart, XAxis, YAxis } from "recharts";
import { useLiveChartData } from "@/data/liveData";

export function ElectronFluxChart() {
  const data = useLiveChartData();

  return (
    <div
      className="w-full h-full p-4 flex flex-col rounded-2xl"
      style={{
        background: "linear-gradient(160deg, #111520 0%, #0d1117 100%)",
        border: "1px solid #1e2230",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-xs font-semibold text-white/70 tracking-wide uppercase">Electron Flux</h3>
          <p className="text-[10px] text-white/30 mt-0.5 font-mono">GOES-16 · e/cm²/s/sr</p>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono text-white/35">
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-px" style={{ background: "linear-gradient(90deg, #4a90a4, #6ab3c8)" }} />
            Historical
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-px bg-white/60" />
            Current
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-px" style={{ background: "rgba(163,48,48,0.7)", borderTop: "1px dashed rgba(163,48,48,0.7)" }} />
            Threshold
          </div>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="gradHistorical" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#4a90a4" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#4a90a4" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradCurrent" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="rgba(255,255,255,0.8)" stopOpacity={0.1} />
                <stop offset="95%" stopColor="rgba(255,255,255,0.8)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="time"
              stroke="rgba(255,255,255,0.1)"
              tick={{ fill: "rgba(255,255,255,0.25)", fontSize: 9 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
            />
            <YAxis
              scale="log"
              domain={["auto", "auto"]}
              stroke="rgba(255,255,255,0.1)"
              tick={{ fill: "rgba(255,255,255,0.25)", fontSize: 9 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(val) => val.toExponential(0)}
            />
            <Tooltip
              contentStyle={{
                background: "linear-gradient(135deg, #1a1d26, #13161e)",
                border: "1px solid #2a2d38",
                borderRadius: "10px",
                fontSize: "11px",
                color: "rgba(255,255,255,0.75)",
                boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
              }}
              labelStyle={{ color: "rgba(255,255,255,0.4)", marginBottom: "4px", fontSize: "10px" }}
              cursor={{ stroke: "rgba(255,255,255,0.1)", strokeWidth: 1 }}
            />
            <ReferenceLine y={10000} stroke="rgba(163,48,48,0.5)" strokeDasharray="4 3" strokeWidth={1} />
            <Area type="monotone" dataKey="historical" stroke="#4a90a4" strokeWidth={1.5} fill="url(#gradHistorical)" dot={false} isAnimationActive={false} />
            <Area type="monotone" dataKey="current" stroke="rgba(255,255,255,0.7)" strokeWidth={1.5} fill="url(#gradCurrent)" dot={false} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
