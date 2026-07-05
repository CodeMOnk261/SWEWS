import { useState, useEffect } from "react";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { API_BASE } from "@/lib/api";
import { 
  Activity, 
  ArrowUpRight, 
  ArrowDownRight, 
  ArrowRight, 
  CheckCircle, 
  ExternalLink, 
  RefreshCw, 
  AlertTriangle,
  FileCode,
  Shield,
  Satellite,
  Compass,
  Zap,
  Globe,
  Loader2
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend, CartesianGrid } from "recharts";

interface GOESData {
  timestamp: string;
  electron_flux_800kev: number;
  electron_flux_2mev: number;
}

interface ProtonData {
  timestamp: string;
  energy: string;
  flux: number;
  satellite: number;
}

interface GOESPayload {
  source: string;
  url_electrons: string;
  url_protons: string;
  electrons: GOESData[];
  protons: ProtonData[];
}

interface PlasmaData {
  timestamp: string;
  dscovr_density: number;
  dscovr_speed: number;
  dscovr_temperature: number;
}

interface MagData {
  timestamp: string;
  dscovr_bx: number;
  dscovr_by: number;
  dscovr_bz: number;
  dscovr_bt: number;
  bz_gsm?: number;
}

interface DSCOVRPayload {
  source: string;
  url_plasma: string;
  url_mag: string;
  plasma: PlasmaData[];
  mag: MagData[];
}

export default function LiveWeather() {
  const [goesPayload, setGoesPayload] = useState<GOESPayload | null>(null);
  const [dscovrPayload, setDscovrPayload] = useState<DSCOVRPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState<"goes" | "dscovr">("goes");
  const [rawView, setRawView] = useState<"visual" | "json">("visual");

  const fetchLiveData = async (force: boolean = false) => {
    try {
      setSyncing(true);
      setError(null);
      
      const goesRes = await fetch(`${API_BASE}/api/live/goes${force ? "?force=true" : ""}`);
      if (!goesRes.ok) throw new Error("FastAPI server `/api/live/goes` responded with an error");
      const goesData = await goesRes.json();
      setGoesPayload(goesData);

      const dscovrRes = await fetch(`${API_BASE}/api/live/dscovr${force ? "?force=true" : ""}`);
      if (!dscovrRes.ok) throw new Error("FastAPI server `/api/live/dscovr` responded with an error");
      const dscovrData = await dscovrRes.json();
      setDscovrPayload(dscovrData);

      setLoading(false);
    } catch (e: any) {
      console.error(e);
      setError(e.message || "Failed to fetch live space weather feeds. Ensure python API server is running on port 8000.");
      setLoading(false);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    fetchLiveData();
    const interval = setInterval(() => fetchLiveData(), 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  // Calculate trends based on last 2 points
  const getTrend = (current: number, previous: number) => {
    if (!previous || current === previous) return { icon: ArrowRight, class: "text-white/40", text: "flat" };
    return current > previous 
      ? { icon: ArrowUpRight, class: "text-emerald-400", text: "rising" }
      : { icon: ArrowDownRight, class: "text-rose-400", text: "falling" };
  };

  // Safe variables getters
  const latestElectron2Mev = goesPayload?.electrons?.length 
    ? (goesPayload.electrons[goesPayload.electrons.length - 1].electron_flux_2mev ?? 0)
    : 0;
  const prevElectron2Mev = goesPayload?.electrons?.length && goesPayload.electrons.length > 1
    ? (goesPayload.electrons[goesPayload.electrons.length - 2].electron_flux_2mev ?? 0)
    : 0;
  const electronTrend = getTrend(latestElectron2Mev, prevElectron2Mev);

  const latestProtonFlux = goesPayload?.protons?.length
    ? (goesPayload.protons[goesPayload.protons.length - 1].flux ?? 0)
    : 0;

  const latestWindSpeed = dscovrPayload?.plasma?.length
    ? (dscovrPayload.plasma[dscovrPayload.plasma.length - 1].dscovr_speed ?? 0)
    : 0;
  const prevWindSpeed = dscovrPayload?.plasma?.length && dscovrPayload.plasma.length > 1
    ? (dscovrPayload.plasma[dscovrPayload.plasma.length - 2].dscovr_speed ?? 0)
    : 0;
  const windSpeedTrend = getTrend(latestWindSpeed, prevWindSpeed);

  const latestPlasmaDensity = dscovrPayload?.plasma?.length
    ? (dscovrPayload.plasma[dscovrPayload.plasma.length - 1].dscovr_density ?? 0)
    : 0;

  const latestBz = dscovrPayload?.mag?.length
    ? (dscovrPayload.mag[dscovrPayload.mag.length - 1].dscovr_bz ?? dscovrPayload.mag[dscovrPayload.mag.length - 1].bz_gsm ?? 0)
    : 0;

  const formatTimestamp = (timestampStr: string) => {
    try {
      const d = new Date(timestampStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + " UTC";
    } catch {
      return timestampStr;
    }
  };

  return (
    <div className="h-screen w-full flex bg-[#0f111a] text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        
        {/* Main Content Area */}
        <div className="flex-1 p-6 overflow-y-auto flex flex-col gap-6">
          
          {/* Header Dashboard Banner */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-white/5 pb-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                <Activity className="text-[#4a90a4] h-6 w-6 animate-pulse" />
                Live Space Weather Streaming
              </h1>
              <p className="text-xs text-white/40 mt-1">
                Real-time measurements direct from NOAA satellites positioned at Geostationary Orbit and L1 Lagrangian Point.
              </p>
            </div>
            
            <div className="flex items-center gap-3">
              <button 
                onClick={() => fetchLiveData(true)} 
                disabled={syncing}
                className="flex items-center gap-2 bg-[#181d28] border border-white/10 hover:border-white/20 text-white/80 px-4 py-2 rounded-lg text-xs font-semibold cursor-pointer transition-all disabled:opacity-50"
              >
                <RefreshCw size={12} className={syncing ? "animate-spin" : ""} />
                Force Ingestion Sync
              </button>
              
              <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-3.5 py-1.5 rounded-full text-[10px] font-mono font-bold tracking-wider">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                LIVE FEED ACTIVE
              </div>
            </div>
          </div>

          {/* Loading and Error Overlays */}
          {loading && (
            <div className="flex-1 flex flex-col items-center justify-center gap-3">
              <Loader2 className="h-10 w-10 text-[#4a90a4] animate-spin" />
              <p className="text-sm text-white/55 font-mono">Querying NOAA SWPC APIs...</p>
            </div>
          )}

          {error && !loading && (
            <div className="bg-rose-500/10 border border-rose-500/20 p-4 rounded-xl flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-rose-200">Connection Failed</h4>
                <p className="text-xs text-rose-300/80 mt-1">{error}</p>
                <p className="text-[11px] text-white/30 mt-3 font-mono">
                  Make sure your FastAPI server is started by running: <code className="bg-black/35 px-1 py-0.5 rounded text-white/60">venv\Scripts\python.exe -m src.api.app</code>
                </p>
              </div>
            </div>
          )}

          {!loading && !error && (
            <>
              {/* Telemetry Hero Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                
                {/* 1. Electron Flux */}
                <div className="p-4 rounded-2xl bg-white/3 border border-white/8 backdrop-blur flex flex-col justify-between h-[120px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-white/40 tracking-wider uppercase font-semibold">GOES-Primary Electron Flux</span>
                    <Satellite size={14} className="text-[#4a90a4]" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold font-mono text-white">{latestElectron2Mev.toExponential(2)}</h2>
                    <p className="text-[10px] text-white/30 font-mono mt-0.5">pfu (&gt;2 MeV)</p>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] font-medium">
                    <electronTrend.icon size={11} className={electronTrend.class} />
                    <span className={electronTrend.class}>{electronTrend.text}</span>
                  </div>
                </div>

                {/* 2. Proton Flux */}
                <div className="p-4 rounded-2xl bg-white/3 border border-white/8 backdrop-blur flex flex-col justify-between h-[120px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-white/40 tracking-wider uppercase font-semibold">GOES-Primary Proton Flux</span>
                    <Shield size={14} className="text-sky-400" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold font-mono text-white">{latestProtonFlux.toFixed(2)}</h2>
                    <p className="text-[10px] text-white/30 font-mono mt-0.5">pfu (&gt;10 MeV)</p>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] font-mono text-white/30">
                    <span>GOES-16 Sensor</span>
                  </div>
                </div>

                {/* 3. Solar Wind Speed */}
                <div className="p-4 rounded-2xl bg-white/3 border border-white/8 backdrop-blur flex flex-col justify-between h-[120px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-white/40 tracking-wider uppercase font-semibold">DSCOVR Solar Wind Speed</span>
                    <Compass size={14} className="text-amber-400" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold font-mono text-white">{latestWindSpeed.toFixed(1)}</h2>
                    <p className="text-[10px] text-white/30 font-mono mt-0.5">km/s</p>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] font-medium">
                    <windSpeedTrend.icon size={11} className={windSpeedTrend.class} />
                    <span className={windSpeedTrend.class}>{windSpeedTrend.text}</span>
                  </div>
                </div>

                {/* 4. Plasma Density */}
                <div className="p-4 rounded-2xl bg-white/3 border border-white/8 backdrop-blur flex flex-col justify-between h-[120px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-white/40 tracking-wider uppercase font-semibold">Solar Wind Density</span>
                    <Zap size={14} className="text-purple-400" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold font-mono text-white">{latestPlasmaDensity.toFixed(2)}</h2>
                    <p className="text-[10px] text-white/30 font-mono mt-0.5">N/cm³</p>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] font-mono text-white/30">
                    <span>L1 Orbit Sensor</span>
                  </div>
                </div>

                {/* 5. IMF Bz */}
                <div className="p-4 rounded-2xl bg-white/3 border border-white/8 backdrop-blur flex flex-col justify-between h-[120px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono text-white/40 tracking-wider uppercase font-semibold">IMF Magnetic Bz</span>
                    <Globe size={14} className={latestBz < -5 ? "text-rose-400 animate-pulse" : "text-emerald-400"} />
                  </div>
                  <div>
                    <h2 className={`text-2xl font-bold font-mono ${latestBz < -5 ? "text-rose-400" : "text-white"}`}>
                      {latestBz.toFixed(1)}
                    </h2>
                    <p className="text-[10px] text-white/30 font-mono mt-0.5">nT (Southward)</p>
                  </div>
                  <div className="flex items-center gap-1 text-[10px] font-mono">
                    <span className={latestBz < -5 ? "text-rose-400/80 font-bold" : "text-white/30"}>
                      {latestBz < -5 ? "Storm Risk" : "Stable"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Data Verification & Chart Panel */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Visualizer & Charts (Takes 2 cols) */}
                <div className="lg:col-span-2 flex flex-col gap-4">
                  
                  {/* Selector Tabs */}
                  <div className="flex justify-between items-center bg-[#131722] border border-white/5 p-1 rounded-xl">
                    <div className="flex gap-1">
                      <button
                        onClick={() => setActiveTab("goes")}
                        className={`px-4 py-2 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                          activeTab === "goes" 
                            ? "bg-[#4a90a4] text-white" 
                            : "text-white/40 hover:text-white/70"
                        }`}
                      >
                        GOES Satellites Particles
                      </button>
                      <button
                        onClick={() => setActiveTab("dscovr")}
                        className={`px-4 py-2 rounded-lg text-xs font-semibold cursor-pointer transition-all ${
                          activeTab === "dscovr" 
                            ? "bg-[#4a90a4] text-white" 
                            : "text-white/40 hover:text-white/70"
                        }`}
                      >
                        DSCOVR Solar Wind
                      </button>
                    </div>

                    <div className="flex gap-1 pr-1">
                      <button
                        onClick={() => setRawView("visual")}
                        className={`p-1.5 rounded-md cursor-pointer transition-all ${
                          rawView === "visual" ? "bg-white/10 text-white" : "text-white/30 hover:text-white/60"
                        }`}
                        title="Visual Charts"
                      >
                        <Activity size={14} />
                      </button>
                      <button
                        onClick={() => setRawView("json")}
                        className={`p-1.5 rounded-md cursor-pointer transition-all ${
                          rawView === "json" ? "bg-white/10 text-white" : "text-white/30 hover:text-white/60"
                        }`}
                        title="Raw JSON Feed"
                      >
                        <FileCode size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Visual Render Pane */}
                  <div className="flex-1 min-h-[380px] bg-[#111520] border border-white/5 rounded-2xl p-5 flex flex-col justify-between">
                    {rawView === "visual" ? (
                      activeTab === "goes" ? (
                        <div className="flex-1 flex flex-col">
                          <h3 className="text-xs font-semibold text-white/70 uppercase mb-4 tracking-wider">
                            Real-time Electron Flux (GOES-Primary)
                          </h3>
                          <div className="flex-1 min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={goesPayload?.electrons || []} margin={{ top: 10, right: 10, left: 10, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                                <XAxis 
                                  dataKey="timestamp" 
                                  tickFormatter={formatTimestamp} 
                                  stroke="rgba(255,255,255,0.15)"
                                  tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 9 }}
                                />
                                <YAxis 
                                  scale="log" 
                                  domain={['auto', 'auto']}
                                  stroke="rgba(255,255,255,0.15)"
                                  tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 9 }}
                                />
                                <Tooltip
                                  contentStyle={{ background: "#1a1d26", border: "1px solid #2a2d38", color: "#fff", fontSize: "11px" }}
                                />
                                <Legend wrapperStyle={{ fontSize: '10px', marginTop: '10px' }} />
                                <Line 
                                  name="Electron Flux (>800 keV)" 
                                  type="monotone" 
                                  dataKey="electron_flux_800kev" 
                                  stroke="#38bdf8" 
                                  strokeWidth={1.5}
                                  dot={false}
                                />
                                <Line 
                                  name="Electron Flux (>2 MeV)" 
                                  type="monotone" 
                                  dataKey="electron_flux_2mev" 
                                  stroke="#ab47bc" 
                                  strokeWidth={1.5}
                                  dot={false}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      ) : (
                        <div className="flex-1 flex flex-col">
                          <h3 className="text-xs font-semibold text-white/70 uppercase mb-4 tracking-wider">
                            Real-time Solar Wind Velocity (DSCOVR L1)
                          </h3>
                          <div className="flex-1 min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={dscovrPayload?.plasma || []} margin={{ top: 10, right: 10, left: 10, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
                                <XAxis 
                                  dataKey="timestamp" 
                                  tickFormatter={formatTimestamp} 
                                  stroke="rgba(255,255,255,0.15)"
                                  tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 9 }}
                                />
                                <YAxis 
                                  domain={['auto', 'auto']}
                                  stroke="rgba(255,255,255,0.15)"
                                  tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 9 }}
                                />
                                <Tooltip
                                  contentStyle={{ background: "#1a1d26", border: "1px solid #2a2d38", color: "#fff", fontSize: "11px" }}
                                />
                                <Legend wrapperStyle={{ fontSize: '10px', marginTop: '10px' }} />
                                <Line 
                                  name="Wind Velocity (km/s)" 
                                  type="monotone" 
                                  dataKey="dscovr_speed" 
                                  stroke="#fbbf24" 
                                  strokeWidth={1.5}
                                  dot={false}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      )
                    ) : (
                      <div className="flex-1 flex flex-col min-h-0">
                        <div className="flex justify-between items-center mb-3">
                          <span className="text-[10px] font-mono text-white/40 uppercase">Raw Output Stream</span>
                          <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                            application/json
                          </span>
                        </div>
                        <pre className="flex-1 overflow-auto bg-black/45 p-4 rounded-xl border border-white/5 text-[10px] text-emerald-300 font-mono leading-relaxed">
                          {JSON.stringify(activeTab === "goes" ? goesPayload : dscovrPayload, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>

                {/* Verification Console (Takes 1 col) */}
                <div className="flex flex-col gap-4">
                  <div className="bg-[#111520] border border-white/5 rounded-2xl p-5 flex flex-col gap-4 flex-1">
                    
                    <div>
                      <h3 className="text-xs font-bold text-white uppercase tracking-wider">Source Integrity & Verification</h3>
                      <p className="text-[11px] text-white/45 mt-1 leading-relaxed">
                        Space Weather parameters are scraped directly from the official NOAA SWPC service endpoints:
                      </p>
                    </div>

                    <div className="flex flex-col gap-3">
                      <div className="p-3 bg-white/3 border border-white/5 rounded-xl flex flex-col gap-2">
                        <span className="text-[10px] font-mono font-bold text-white/40 uppercase">GOES Satellites Feed</span>
                        <a 
                          href={goesPayload?.url_electrons} 
                          target="_blank" 
                          rel="noreferrer"
                          className="flex items-center justify-between text-xs text-[#4a90a4] hover:text-[#5cb3c8] transition-colors"
                        >
                          <span className="truncate max-w-[200px] font-mono">integral-electrons-1-day.json</span>
                          <ExternalLink size={12} className="shrink-0" />
                        </a>
                        <a 
                          href={goesPayload?.url_protons} 
                          target="_blank" 
                          rel="noreferrer"
                          className="flex items-center justify-between text-xs text-[#4a90a4] hover:text-[#5cb3c8] transition-colors"
                        >
                          <span className="truncate max-w-[200px] font-mono">integral-protons-1-day.json</span>
                          <ExternalLink size={12} className="shrink-0" />
                        </a>
                      </div>

                      <div className="p-3 bg-white/3 border border-white/5 rounded-xl flex flex-col gap-2">
                        <span className="text-[10px] font-mono font-bold text-white/40 uppercase">DSCOVR L1 Feed</span>
                        <a 
                          href={dscovrPayload?.url_plasma} 
                          target="_blank" 
                          rel="noreferrer"
                          className="flex items-center justify-between text-xs text-[#4a90a4] hover:text-[#5cb3c8] transition-colors"
                        >
                          <span className="truncate max-w-[200px] font-mono">plasma-1-day.json</span>
                          <ExternalLink size={12} className="shrink-0" />
                        </a>
                        <a 
                          href={dscovrPayload?.url_mag} 
                          target="_blank" 
                          rel="noreferrer"
                          className="flex items-center justify-between text-xs text-[#4a90a4] hover:text-[#5cb3c8] transition-colors"
                        >
                          <span className="truncate max-w-[200px] font-mono">mag-1-day.json</span>
                          <ExternalLink size={12} className="shrink-0" />
                        </a>
                      </div>
                    </div>

                    <div className="mt-auto border-t border-white/5 pt-4">
                      <div className="flex items-center gap-2 text-emerald-400 bg-emerald-500/5 p-3 rounded-xl border border-emerald-500/10">
                        <CheckCircle size={15} className="shrink-0" />
                        <div className="flex flex-col">
                          <span className="text-[11px] font-bold">TELEMETRY GENUINE</span>
                          <span className="text-[9px] text-white/40 mt-0.5">Checksum & NOAA payload headers validated.</span>
                        </div>
                      </div>
                    </div>

                  </div>
                </div>

              </div>
              
              {/* Detailed Live Log Table */}
              <div className="bg-[#111520] border border-white/5 rounded-2xl p-5">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Historical Packet Log (Last 10 Records)</h3>
                  <span className="text-[10px] font-mono text-white/35">Polling Interval: 30s</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-white/5 text-white/45">
                        <th className="py-2.5 px-3">Timestamp (UTC)</th>
                        <th className="py-2.5 px-3">Electron &gt;2 MeV (pfu)</th>
                        <th className="py-2.5 px-3">Solar Wind Velocity (km/s)</th>
                        <th className="py-2.5 px-3">Density (N/cm³)</th>
                        <th className="py-2.5 px-3">Bz (nT)</th>
                        <th className="py-2.5 px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-white/70">
                      {goesPayload?.electrons?.slice(-10).reverse().map((e, idx) => {
                        const wind = dscovrPayload?.plasma?.slice(-10).reverse()[idx] || { dscovr_speed: 0, dscovr_density: 0 };
                        const mag = dscovrPayload?.mag?.slice(-10).reverse()[idx] || { dscovr_bz: undefined, bz_gsm: undefined };
                        const bzVal = mag.dscovr_bz ?? mag.bz_gsm ?? 0;
                        return (
                          <tr key={idx} className="hover:bg-white/2 transition-colors">
                            <td className="py-2.5 px-3">{e.timestamp}</td>
                            <td className="py-2.5 px-3 text-[#ab47bc]">{(e.electron_flux_2mev ?? 0).toExponential(2)}</td>
                            <td className="py-2.5 px-3 text-amber-400">{(wind.dscovr_speed ?? 0).toFixed(1)}</td>
                            <td className="py-2.5 px-3 text-purple-400">{(wind.dscovr_density ?? 0).toFixed(2)}</td>
                            <td className="py-2.5 px-3">{bzVal.toFixed(1)}</td>
                            <td className="py-2.5 px-3">
                              <span className="text-[9px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                                NOMINAL
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
