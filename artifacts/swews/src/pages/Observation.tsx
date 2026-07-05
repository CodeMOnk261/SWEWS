import { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { useDscovrLive } from "@/data/useSpaceWeatherData";
import { 
  Activity, 
  Compass, 
  ExternalLink, 
  Info, 
  Loader2, 
  RefreshCw, 
  Settings, 
  TrendingDown, 
  TrendingUp, 
  Waves, 
  Zap 
} from "lucide-react";
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  ResponsiveContainer, 
  Tooltip, 
  CartesianGrid, 
  BarChart, 
  Bar, 
  Cell 
} from "recharts";

export default function Observation() {
  const { data: dscovrPayload, isLoading, error, refetch, isFetching } = useDscovrLive();
  const [activeTab, setActiveTab] = useState<"field_plasma" | "ions_electrons">("field_plasma");
  
  // Format timestamp helper
  const formatTimestamp = (timestampStr: string) => {
    try {
      const d = new Date(timestampStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) + "Z";
    } catch {
      return timestampStr;
    }
  };

  // Process data for charts
  const getProcessedData = () => {
    if (!dscovrPayload || !dscovrPayload.plasma || !dscovrPayload.mag) return [];
    
    // Align plasma and magnetometer data by matching closest timestamps
    return dscovrPayload.plasma.map((p) => {
      // Find closest mag point
      const magPoint = dscovrPayload.mag.find((m) => m.timestamp === p.timestamp) || 
                       dscovrPayload.mag[0] || {};
      
      const bx = magPoint.dscovr_bx ?? 0;
      const by = magPoint.dscovr_by ?? 0;
      const bz = magPoint.dscovr_bz ?? magPoint.bz_gsm ?? 0;
      const bt = magPoint.dscovr_bt ?? Math.sqrt(bx*bx + by*by + bz*bz);
      
      // Calculate Phi (angle of IMF in degrees, 0 to 360)
      let phi = Math.atan2(by, bx) * (180 / Math.PI);
      if (phi < 0) phi += 360;

      // Approximate Kp index based on solar wind speed and southward Bz
      const bz_intensity = Math.max(0.0, -bz / 18.0);
      const speed_intensity = Math.max(0.0, (p.dscovr_speed - 400.0) / 500.0);
      const intensity = 0.15 * speed_intensity + 0.85 * bz_intensity;
      const kp = Math.max(0, Math.min(9, 1.4 + intensity * 7.2));

      return {
        time: p.timestamp,
        formattedTime: formatTimestamp(p.timestamp),
        bx: parseFloat(bx.toFixed(2)),
        by: parseFloat(by.toFixed(2)),
        bz: parseFloat(bz.toFixed(2)),
        bt: parseFloat(bt.toFixed(2)),
        phi: Math.round(phi),
        density: parseFloat(p.dscovr_density.toFixed(2)),
        speed: Math.round(p.dscovr_speed),
        temperature: Math.round(p.dscovr_temperature),
        kp: parseFloat(kp.toFixed(1))
      };
    }).slice(-120); // Keep last 120 observations (~10 hours)
  };

  const chartData = getProcessedData();

  // Custom tooltips to align look-and-feel
  const CustomChartTooltip = ({ active, payload, label, unit = "" }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#121622] border border-white/10 p-2.5 rounded-lg shadow-xl font-mono text-[10px]">
          <p className="text-white/40 mb-1 border-b border-white/5 pb-1">{label}</p>
          {payload.map((item: any, i: number) => (
            <div key={i} className="flex justify-between items-center gap-4 py-0.5">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="text-white/70">{item.name}:</span>
              </span>
              <span className="font-bold text-white" style={{ color: item.color }}>
                {item.value} {unit}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="h-screen w-full flex bg-[#0d1017] text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />

        {/* Dashboard Container */}
        <div className="flex-1 p-5 overflow-y-auto flex flex-col gap-4">
          
          {/* Header Area */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-white/5 pb-3">
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                <Waves className="text-[#6ab3c8] h-5 w-5 animate-pulse" />
                SOLAR WIND OBSERVATIONS
                <span className="text-[10px] bg-sky-500/10 border border-sky-500/20 text-[#6ab3c8] px-2 py-0.5 rounded font-mono font-normal">
                  EXPERIMENTAL DISPLAY
                </span>
              </h1>
              <p className="text-[11px] text-white/40 mt-0.5">
                Stacked solar wind telemetry from DSCOVR at L1 Lagrangian point, styled similarly to NASA/NOAA experimental monitors.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button 
                onClick={() => refetch()} 
                disabled={isFetching}
                className="flex items-center gap-1.5 bg-[#171b26] border border-white/10 hover:border-white/20 text-white/80 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all disabled:opacity-50"
              >
                <RefreshCw size={11} className={isFetching ? "animate-spin" : ""} />
                Sync Telemetry
              </button>
              <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold tracking-wide">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                DSCOVR L1 STREAM
              </div>
            </div>
          </div>

          {/* Sub Header & Selector Controls */}
          <div className="flex flex-col md:flex-row justify-between items-stretch md:items-center gap-3 bg-[#131722] border border-white/5 p-2 rounded-xl">
            {/* Display Tabs */}
            <div className="flex gap-1.5 bg-[#0d1017] p-1 rounded-lg border border-white/5 self-start">
              <button
                onClick={() => setActiveTab("field_plasma")}
                className={`px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-all ${
                  activeTab === "field_plasma" 
                    ? "bg-[#6ab3c8] text-gray-950 font-bold" 
                    : "text-white/40 hover:text-white/70"
                }`}
              >
                Magnetic Field and Plasma
              </button>
              <button
                onClick={() => setActiveTab("ions_electrons")}
                className={`px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition-all ${
                  activeTab === "ions_electrons" 
                    ? "bg-[#6ab3c8] text-gray-950 font-bold" 
                    : "text-white/40 hover:text-white/70"
                }`}
              >
                Suprathermal Ions and Electrons
              </button>
            </div>

            {/* Source selectors dropdowns simulation */}
            <div className="flex items-center gap-2 text-[11px] text-white/40 font-mono">
              <div className="flex items-center gap-1 bg-[#171b26] border border-white/10 px-2 py-1.5 rounded-md">
                <span>IMF:</span>
                <span className="text-[#6ab3c8] font-bold">DSCOVR</span>
                <Settings size={10} className="text-white/30 ml-1 cursor-pointer hover:text-white/60" />
              </div>
              <div className="flex items-center gap-1 bg-[#171b26] border border-white/10 px-2 py-1.5 rounded-md">
                <span>Plasma:</span>
                <span className="text-[#6ab3c8] font-bold">DSCOVR</span>
                <Settings size={10} className="text-white/30 ml-1 cursor-pointer hover:text-white/60" />
              </div>
            </div>
          </div>

          {/* Loading & Error States */}
          {isLoading && (
            <div className="flex-1 flex flex-col items-center justify-center gap-3">
              <Loader2 className="h-10 w-10 text-[#6ab3c8] animate-spin" />
              <p className="text-sm text-white/55 font-mono">Fetching solar wind data points...</p>
            </div>
          )}

          {error && (
            <div className="flex-1 bg-rose-500/5 border border-rose-500/10 p-5 rounded-2xl flex flex-col items-center justify-center text-center">
              <Activity className="h-10 w-10 text-rose-400 mb-3 animate-pulse" />
              <h3 className="text-sm font-semibold text-rose-200">NOAA Feed Offline</h3>
              <p className="text-xs text-rose-300/60 mt-1 max-w-sm">
                Failed to communicate with the local FastAPI ingestion microservice. Check that the service is running.
              </p>
            </div>
          )}

          {/* Stacked Chart Panel */}
          {!isLoading && !error && chartData.length > 0 && (
            <div className="flex-1 bg-[#111420] border border-white/5 rounded-2xl p-4 flex flex-col gap-1 overflow-y-auto">
              
              {/* Plot 1: IMF GSM (nT) */}
              <div className="h-[120px] relative border-b border-white/5 pb-2">
                <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-white/60 uppercase">IMF GSM (nT)</span>
                  <span title="Interplanetary Magnetic Field components in GSM coordinates" className="cursor-help flex items-center">
                    <Info size={10} className="text-white/20" />
                  </span>
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} syncId="solarWindSync" margin={{ top: 20, right: 30, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <YAxis 
                      domain={['auto', 'auto']} 
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 8 }}
                      width={35}
                    />
                    <Tooltip content={<CustomChartTooltip unit="nT" />} />
                    <Line name="|Bt|" type="monotone" dataKey="bt" stroke="#ffffff" strokeWidth={1} dot={false} />
                    <Line name="Bz (Southward)" type="monotone" dataKey="bz" stroke="#ef4444" strokeWidth={1} dot={false} />
                    <Line name="Bx" type="monotone" dataKey="bx" stroke="#a855f7" strokeWidth={1} dot={false} />
                    <Line name="By" type="monotone" dataKey="by" stroke="#06b6d4" strokeWidth={1} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Plot 2: Phi GSM (deg) */}
              <div className="h-[120px] relative border-b border-white/5 pb-2">
                <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-white/60 uppercase">Phi GSM (deg)</span>
                  <span title="IMF longitude/azimuthal angle" className="cursor-help flex items-center">
                    <Info size={10} className="text-white/20" />
                  </span>
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} syncId="solarWindSync" margin={{ top: 20, right: 30, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <YAxis 
                      domain={[0, 360]} 
                      ticks={[0, 90, 180, 270, 360]}
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 8 }}
                      width={35}
                    />
                    <Tooltip content={<CustomChartTooltip unit="°" />} />
                    <Line name="Phi" type="monotone" dataKey="phi" stroke="#f59e0b" strokeWidth={1.2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Plot 3: Density 1/cm³ */}
              <div className="h-[120px] relative border-b border-white/5 pb-2">
                <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-white/60 uppercase">Density (1/cm³)</span>
                  <span title="Solar wind proton density" className="cursor-help flex items-center">
                    <Info size={10} className="text-white/20" />
                  </span>
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} syncId="solarWindSync" margin={{ top: 20, right: 30, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <YAxis 
                      domain={['auto', 'auto']}
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 8 }}
                      width={35}
                    />
                    <Tooltip content={<CustomChartTooltip unit="n/cc" />} />
                    <Line name="Density" type="monotone" dataKey="density" stroke="#10b981" strokeWidth={1.2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Plot 4: Speed km/s */}
              <div className="h-[120px] relative border-b border-white/5 pb-2">
                <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-white/60 uppercase">Speed (km/s)</span>
                  <span title="Solar wind bulk velocity speed" className="cursor-help flex items-center">
                    <Info size={10} className="text-white/20" />
                  </span>
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} syncId="solarWindSync" margin={{ top: 20, right: 30, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <YAxis 
                      domain={['auto', 'auto']}
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 8 }}
                      width={35}
                    />
                    <Tooltip content={<CustomChartTooltip unit="km/s" />} />
                    <Line name="Speed" type="monotone" dataKey="speed" stroke="#3b82f6" strokeWidth={1.2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Plot 5: Temperature (K) */}
              <div className="h-[120px] relative border-b border-white/5 pb-2">
                <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-white/60 uppercase">Temperature (K)</span>
                  <span title="Solar wind proton thermal temperature" className="cursor-help flex items-center">
                    <Info size={10} className="text-white/20" />
                  </span>
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} syncId="solarWindSync" margin={{ top: 20, right: 30, left: 20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <YAxis 
                      domain={['auto', 'auto']}
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ 
                        fill: "rgba(255,255,255,0.3)", 
                        fontSize: 8 
                      }}
                      tickFormatter={(val) => val.toExponential(0)}
                      width={35}
                    />
                    <Tooltip content={<CustomChartTooltip unit="K" />} />
                    <Line name="Temperature" type="monotone" dataKey="temperature" stroke="#ec4899" strokeWidth={1.2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Plot 6: Kp index (Unified X-Axis at Bottom) */}
              <div className="h-[125px] relative">
                <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold text-white/60 uppercase">Kp index</span>
                  <span title="Planetary Kp index computed dynamically from solar wind input" className="cursor-help flex items-center">
                    <Info size={10} className="text-white/20" />
                  </span>
                </div>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} syncId="solarWindSync" margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                    <XAxis 
                      dataKey="formattedTime" 
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 8 }}
                    />
                    <YAxis 
                      domain={[0, 9]}
                      ticks={[0, 3, 6, 9]}
                      stroke="rgba(255,255,255,0.15)"
                      tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 8 }}
                      width={35}
                    />
                    <Tooltip content={<CustomChartTooltip unit="" />} />
                    <Bar name="Kp index" dataKey="kp" maxBarSize={15}>
                      {chartData.map((entry, index) => {
                        let barColor = "#10b981"; // Quiet
                        if (entry.kp >= 6) barColor = "#ef4444"; // Storm
                        else if (entry.kp >= 4) barColor = "#f59e0b"; // Active
                        return <Cell key={`cell-${index}`} fill={barColor} opacity={0.8} />;
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

            </div>
          )}

        </div>
      </div>
    </div>
  );
}
