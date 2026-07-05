import { Activity, Globe, LayoutDashboard, LineChart, Radio, ShieldAlert } from "lucide-react";
import { Link, useLocation } from "wouter";

export function Sidebar() {
  const [location] = useLocation();

  const links = [
    { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { href: "/observation", icon: LineChart, label: "Solar Wind" },
    { href: "/live", icon: Activity, label: "Live Weather" },
  ];

  return (
    <div
      className="w-[56px] h-full flex flex-col items-center py-3 shrink-0"
      style={{
        background: "linear-gradient(180deg, #111520 0%, #0d1117 100%)",
        borderRight: "1px solid #1e2230",
      }}
    >
      <div className="mb-4 w-8 h-8 flex items-center justify-center">
        <img src="/logo.png" alt="SWEWS" className="w-6 h-6 object-contain opacity-70" />
      </div>
      <div className="w-full h-px bg-white/5 mb-3" />
      <div className="flex-1 flex flex-col gap-1 w-full px-2">
        {links.map(({ href, icon: Icon, label }) => {
          const isActive = location === href;
          return (
            <Link key={href} href={href} className="w-full">
              <div
                title={label}
                className={`relative flex items-center justify-center w-full h-9 rounded-lg cursor-pointer transition-all duration-150 ${
                  isActive
                    ? "bg-white/10 text-white"
                    : "text-white/30 hover:text-white/60 hover:bg-white/5"
                }`}
              >
                {isActive && (
                  <div
                    className="absolute left-0 top-1 bottom-1 w-[2px] rounded-full"
                    style={{ background: "linear-gradient(180deg, #6ab3c8, #4a90a4)" }}
                  />
                )}
                <Icon size={16} strokeWidth={isActive ? 2 : 1.5} />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
