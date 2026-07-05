import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { FreshEarthVisualizer } from "@/components/FreshEarthVisualizer";
import { ElectronFluxLiveChart } from "@/components/ElectronFluxLiveChart";
import { AlertWindow } from "@/components/AlertWindow";
import { LiveTelemetry } from "@/components/LiveTelemetry";
import { StormProbability } from "@/components/StormProbability";

export default function Dashboard() {
  return (
    <div className="h-screen w-full flex bg-background text-foreground overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 p-4 min-h-0">
          
          {/* Main Workspace (Takes 2 cols) */}
          <div className="lg:col-span-2 flex flex-col gap-4 min-h-0">
            <div className="flex-1 min-h-0">
              <FreshEarthVisualizer />
            </div>
            <div className="h-[250px] shrink-0">
              <ElectronFluxLiveChart />
            </div>
          </div>

          {/* Intelligence Panel */}
          <div className="flex flex-col gap-4 min-h-0">
            <div className="h-[200px] shrink-0">
              <AlertWindow />
            </div>
            <div className="flex-1 min-h-0">
              <LiveTelemetry />
            </div>
            <div className="shrink-0">
              <StormProbability />
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
