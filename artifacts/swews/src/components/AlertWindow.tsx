import { useLiveAlerts } from "@/data/liveData";
import { AlertCircle, AlertTriangle, Info, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export function AlertWindow() {
  const { alerts, dismissAlert } = useLiveAlerts();

  return (
    <div className="flex flex-col gap-2 h-full overflow-hidden">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-[10px] font-semibold text-white/35 uppercase tracking-widest">Smart Alerts</h3>
        <span className="text-[10px] font-mono text-white/20">{alerts.length} active</span>
      </div>
      <div className="flex-1 overflow-y-auto space-y-1.5 pr-0.5">
        <AnimatePresence>
          {alerts.map((alert) => {
            const isCrit = alert.severity === "CRITICAL";
            const isWarn = alert.severity === "WARNING";
            const Icon = isCrit ? AlertCircle : isWarn ? AlertTriangle : Info;

            const gradients = {
              CRITICAL: "linear-gradient(135deg, rgba(163,48,48,0.12) 0%, rgba(163,48,48,0.04) 100%)",
              WARNING:  "linear-gradient(135deg, rgba(212,168,67,0.1) 0%, rgba(212,168,67,0.03) 100%)",
              INFO:     "linear-gradient(135deg, rgba(74,144,164,0.1) 0%, rgba(74,144,164,0.03) 100%)",
            };
            const borders = {
              CRITICAL: "rgba(163,48,48,0.25)",
              WARNING:  "rgba(212,168,67,0.22)",
              INFO:     "rgba(74,144,164,0.2)",
            };
            const iconColors = {
              CRITICAL: "#c94040",
              WARNING:  "#c89a30",
              INFO:     "#4a90a4",
            };

            return (
              <motion.div
                key={alert.id}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.2 }}
                className="relative flex items-start gap-3 p-3 rounded-xl group"
                style={{
                  background: gradients[alert.severity],
                  border: `1px solid ${borders[alert.severity]}`,
                }}
                data-testid={`alert-${alert.id}`}
              >
                <Icon size={13} style={{ color: iconColors[alert.severity] }} className="shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-white/80 leading-snug truncate">{alert.title}</p>
                  <p className="text-[10px] text-white/30 mt-0.5 font-mono">{alert.time}</p>
                </div>
                <button
                  onClick={() => dismissAlert(alert.id)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-white/10"
                  data-testid={`dismiss-alert-${alert.id}`}
                >
                  <X size={10} className="text-white/40" />
                </button>
              </motion.div>
            );
          })}
          {alerts.length === 0 && (
            <div className="p-4 text-center text-xs text-white/25 rounded-xl border border-dashed border-white/8">
              No active alerts — system nominal
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
