import { useState, useEffect, useRef } from "react";
import { Link } from "wouter";
import {
  Activity,
  Globe,
  ShieldAlert,
  Twitter,
  Github,
  Linkedin,
  Mail,
  Phone,
  ChevronRight,
  Radio,
  BarChart2,
  Bell,
  ArrowRight,
} from "lucide-react";
import { HeroEarth } from "@/components/HeroEarth";

/* ─── Animated star canvas ──────────────────────────────────────────────── */
function StarField() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf: number;
    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);
    const stars = Array.from({ length: 180 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: Math.random() * 1.2,
      a: 0.1 + Math.random() * 0.55,
      d: (Math.random() - 0.5) * 0.004,
    }));
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      stars.forEach((s) => {
        s.a = Math.max(0.05, Math.min(0.7, s.a + s.d));
        if (s.a <= 0.05 || s.a >= 0.7) s.d *= -1;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${s.a})`;
        ctx.fill();
      });
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);
  return <canvas ref={ref} className="absolute inset-0 w-full h-full pointer-events-none" />;
}

/* ─── Navbar ─────────────────────────────────────────────────────────────── */
function NavBar() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", fn);
    return () => window.removeEventListener("scroll", fn);
  }, []);

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${scrolled ? "bg-[#05080f]/95 backdrop-blur-md border-b border-white/6" : "bg-transparent"}`}>
      <div className="max-w-7xl mx-auto px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <img src="/logo.png" alt="SWEWS" className="w-7 h-7 object-contain opacity-85" data-testid="img-logo-nav" />
          <span className="font-bold text-white/90 tracking-widest text-sm font-mono">SWEWS</span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-sm text-white/45 font-light">
          {["Features","Dashboard","Data","Contact"].map((l) => (
            <a key={l} href={`#${l.toLowerCase()}`} className="hover:text-white/80 transition-colors">{l}</a>
          ))}
        </div>
        <Link href="/dashboard"
          className="flex items-center gap-2 px-5 py-2 rounded-full border border-white/15 text-white/70 text-sm font-medium hover:border-white/30 hover:text-white transition-all"
          data-testid="nav-open-dashboard">
          Open Dashboard <ChevronRight size={13} />
        </Link>
      </div>
    </nav>
  );
}

/* ─── Hero ───────────────────────────────────────────────────────────────── */
const heroStats = [
  { num: "12+", label: "Parameters" },
  { num: "3",   label: "Satellites" },
  { num: "30m", label: "Forecast" },
  { num: "24/7", label: "Monitoring" },
];

function HeroSection() {
  const [utc, setUtc] = useState("");
  useEffect(() => {
    const fn = () => setUtc(new Date().toUTCString().slice(0, -4) + "UTC");
    fn(); const t = setInterval(fn, 1000); return () => clearInterval(t);
  }, []);

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      {/* ── Cinematic background ── */}
      <div className="absolute inset-0">
        {/* Deep space base */}
        <div className="absolute inset-0" style={{
          background: "linear-gradient(160deg, #020610 0%, #040c1e 30%, #02080f 70%, #010306 100%)"
        }} />
        {/* Atmospheric glow — horizon */}
        <div className="absolute bottom-0 left-0 right-0 h-[45%]" style={{
          background: "radial-gradient(ellipse at 65% 120%, rgba(30,80,160,0.35) 0%, rgba(10,40,100,0.15) 35%, transparent 65%)"
        }} />
        {/* Right-side nebula glow behind logo */}
        <div className="absolute top-0 right-0 w-2/3 h-full" style={{
          background: "radial-gradient(ellipse at 80% 45%, rgba(20,60,120,0.28) 0%, rgba(10,30,70,0.12) 40%, transparent 65%)"
        }} />
        {/* Top aurora band */}
        <div className="absolute top-0 left-0 right-0 h-[30%]" style={{
          background: "linear-gradient(180deg, rgba(2,10,30,0.8) 0%, transparent 100%)"
        }} />
        <StarField />
      </div>

      {/* ── Content ── */}
      <div className="relative z-10 max-w-7xl mx-auto px-8 w-full pt-24 pb-20">
        <div className="grid md:grid-cols-2 gap-12 items-center">

          {/* Left — Text */}
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-sm border border-white/12 text-[11px] font-mono text-white/40 tracking-widest uppercase mb-10">
              NOAA GOES-16/18 &nbsp;·&nbsp; v2.4.1
            </div>

            <h1 className="text-6xl md:text-[5.5rem] font-extrabold text-white leading-[0.95] tracking-tight mb-7">
              Space<br />
              <span style={{ color: "#4a90a4" }}>Weather</span><br />
              Warning.
            </h1>

            <p className="text-lg text-white/45 font-light leading-relaxed max-w-md mb-10">
              Research-grade solar event monitoring and geomagnetic storm prediction — built for engineers and satellite operators.
            </p>

            <div className="flex flex-wrap items-center gap-4 mb-14">
              <Link href="/dashboard"
                className="inline-flex items-center gap-2.5 px-7 py-3.5 rounded-full bg-white text-gray-950 font-semibold text-sm hover:bg-white/90 transition-all hover:-translate-y-px"
                data-testid="hero-open-dashboard">
                Open Mission Control
              </Link>
              <a href="#dashboard"
                className="inline-flex items-center gap-2 text-white/50 text-sm font-light hover:text-white/80 transition-colors">
                View interface <ArrowRight size={14} />
              </a>
            </div>

            {/* NASA-style stat numbers */}
            <div className="flex gap-10 border-t border-white/8 pt-10">
              {heroStats.map((s) => (
                <div key={s.num}>
                  <div className="text-4xl font-bold font-mono text-white/90 leading-none mb-1"
                    style={{ fontVariantNumeric: "tabular-nums" }}>
                    {s.num}
                  </div>
                  <div className="text-[11px] font-mono text-white/30 uppercase tracking-widest">{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Right — Earth + satellite + Van Allen belts */}
          <div className="flex items-center justify-center">
            <HeroEarth />
          </div>

        </div>
      </div>

      {/* Bottom vignette into next section */}
      <div className="absolute bottom-0 left-0 right-0 h-32" style={{
        background: "linear-gradient(180deg, transparent, #0d1117)"
      }} />

      <div className="absolute bottom-6 left-1/2 -translate-x-1/2">
        <p className="text-[10px] font-mono text-white/18 tracking-widest">{utc}</p>
      </div>
    </section>
  );
}

/* ─── Features ───────────────────────────────────────────────────────────── */
const features = [
  { icon: Globe,      title: "2D Solar Wind Model",       desc: "Interactive 2D model showing solar wind streams, bow shock boundary, magnetopause, and Earth's magnetic field deflection." },
  { icon: Activity,   title: "Electron Flux Forecasting", desc: "Scientific charts with historical flux, live measurements, and 30-min to 12-hour predictions with confidence intervals." },
  { icon: Bell,       title: "Smart Alerts",              desc: "Prioritized alerts for CME detections, Kp elevation, stream status, and geomagnetic storm warnings in real time." },
  { icon: Radio,      title: "Live Telemetry",            desc: "Continuous readout of electron flux, proton flux, solar wind speed, IMF Bx/By/Bz, Kp, Dst, AE, and X-ray flux." },
  { icon: ShieldAlert, title: "Satellite Risk",           desc: "Surface charging, deep dielectric, solar panel exposure, communication, and navigation risk scores." },
  { icon: BarChart2,  title: "AI Storm Probability",      desc: "Transformer-based classifier with storm probability, severity classification, model confidence, and variable importance." },
];

function FeaturesSection() {
  return (
    <section id="features" className="bg-[#0d1117] py-28">
      {/* Full-bleed section header — Blender style */}
      <div className="max-w-7xl mx-auto px-8 mb-16">
        <div className="flex items-end justify-between flex-wrap gap-6">
          <div>
            <p className="text-[10px] font-mono text-white/25 tracking-[0.25em] uppercase mb-3">Platform Capabilities</p>
            <h2 className="text-4xl md:text-5xl font-extrabold text-white leading-tight">
              One workspace.<br />
              <span className="text-white/40">Everything you need.</span>
            </h2>
          </div>
          <p className="text-white/35 text-sm font-light max-w-xs leading-relaxed">
            Built for researchers and satellite operators who need accurate space weather data — fast.
          </p>
        </div>
      </div>

      {/* Full-width tile grid */}
      <div className="max-w-7xl mx-auto px-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {features.map((f, i) => (
            <div key={f.title}
              className={`group p-7 rounded-2xl border border-[#1e2230] cursor-default transition-all duration-200 hover:border-[#2e3245] hover:-translate-y-0.5 ${i === 0 ? "bg-[#111520]" : "bg-[#0e1119]"}`}
              data-testid={`feature-card-${f.title.toLowerCase().replace(/\s+/g, '-')}`}>
              <div className="w-11 h-11 rounded-2xl bg-[#181d28] border border-[#252a38] flex items-center justify-center mb-6">
                <f.icon size={19} className="text-white/55" strokeWidth={1.4} />
              </div>
              <h3 className="font-semibold text-white/85 text-[15px] mb-2.5 tracking-tight">{f.title}</h3>
              <p className="text-white/30 text-sm leading-relaxed font-light">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─── Dashboard preview — full-bleed Blender style ──────────────────────── */
function DashboardPreview() {
  return (
    <section id="dashboard" className="bg-[#080c12] py-0 overflow-hidden">
      {/* Section label — above image */}
      <div className="max-w-7xl mx-auto px-8 pt-24 pb-12">
        <p className="text-[10px] font-mono text-white/22 tracking-[0.25em] uppercase mb-4">Mission Control Interface</p>
        <div className="flex items-end justify-between flex-wrap gap-6">
          <h2 className="text-4xl md:text-5xl font-extrabold text-white leading-tight">
            Built for the<br />
            <span className="text-white/35">research floor.</span>
          </h2>
          <Link href="/dashboard"
            className="inline-flex items-center gap-2.5 px-7 py-3.5 rounded-full bg-white text-gray-950 font-semibold text-sm hover:bg-white/90 transition-all hover:-translate-y-px shrink-0"
            data-testid="preview-open-dashboard">
            Open Dashboard <ArrowRight size={15} />
          </Link>
        </div>
      </div>

      {/* Full-bleed image — extends to edges, no max-width */}
      <div className="relative mx-4 md:mx-8 rounded-2xl overflow-hidden border border-white/8"
        style={{ boxShadow: "0 40px 120px rgba(0,0,0,0.8)" }}>
        <img src="/dashboard-preview.png" alt="SWEWS Research Dashboard"
          className="w-full object-cover object-top block"
          data-testid="img-dashboard-preview" />
        {/* Bottom fade */}
        <div className="absolute bottom-0 left-0 right-0 h-1/3"
          style={{ background: "linear-gradient(180deg, transparent, rgba(8,12,18,0.95))" }} />
      </div>

      <div className="pb-24" />
    </section>
  );
}

/* ─── Data sources — Blender colored-band style ─────────────────────────── */
const dataPoints = [
  { label: "NOAA GOES-16/18", detail: "Primary real-time solar imaging & particle data" },
  { label: "DSCOVR Solar Wind", detail: "L1 point interplanetary magnetic field & plasma" },
  { label: "ACE Satellite", detail: "Solar energetic particle event monitoring" },
  { label: "Kp / Dst / AE Indices", detail: "Ground-based magnetometer network data" },
];

function DataSourcesSection() {
  return (
    <section id="data" className="relative overflow-hidden"
      style={{ background: "linear-gradient(135deg, #0e1520 0%, #0a1018 100%)" }}>
      <div className="absolute inset-0 opacity-30" style={{
        background: "radial-gradient(ellipse at 0% 50%, rgba(74,144,164,0.12) 0%, transparent 60%)"
      }} />
      <div className="relative max-w-7xl mx-auto px-8 py-28 grid md:grid-cols-2 gap-20 items-center">
        <div>
          <p className="text-[10px] font-mono text-white/22 tracking-[0.25em] uppercase mb-4">Data Sources</p>
          <h2 className="text-4xl md:text-5xl font-extrabold text-white leading-tight mb-6">
            Authoritative<br />
            <span className="text-white/35">space weather data.</span>
          </h2>
          <p className="text-white/35 font-light leading-relaxed mb-10 max-w-sm">
            SWEWS ingests real-time feeds from NOAA, NASA, and ground-based observatory networks — a single unified view across all critical parameters.
          </p>
          <Link href="/dashboard"
            className="inline-flex items-center gap-2 text-white/50 text-sm font-light hover:text-white/80 transition-colors"
            data-testid="datasources-open-dashboard">
            View live data <ArrowRight size={14} />
          </Link>
        </div>

        <div className="space-y-2">
          {dataPoints.map((d, i) => (
            <div key={i}
              className="flex items-center gap-5 p-5 rounded-2xl border border-white/6 bg-white/3 hover:bg-white/5 hover:border-white/10 transition-all"
              data-testid={`datasource-${i}`}>
              <div className="text-2xl font-bold font-mono text-white/15 w-8 shrink-0 text-right">
                {String(i + 1).padStart(2, "0")}
              </div>
              <div className="w-px h-8 bg-white/10 shrink-0" />
              <div>
                <p className="text-white/70 text-sm font-medium mb-0.5">{d.label}</p>
                <p className="text-white/28 text-xs font-light">{d.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─── Footer ─────────────────────────────────────────────────────────────── */
function Footer() {
  return (
    <footer id="contact" className="bg-[#060a0f] border-t border-white/6 pt-20 pb-10 px-8">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-14 mb-16">
          <div>
            <div className="flex items-center gap-3 mb-5">
              <img src="/logo.png" alt="SWEWS" className="w-9 h-9 object-contain opacity-75" data-testid="img-logo-footer" />
              <span className="font-bold text-white/80 tracking-widest font-mono text-sm">SWEWS</span>
            </div>
            <p className="text-white/28 text-sm font-light leading-relaxed mb-6 max-w-[260px]">
              Space Weather Early Warning System — precision research platform for solar event monitoring and geomagnetic forecasting.
            </p>
            <div className="flex items-center gap-3">
              {[
                { href: "https://twitter.com", icon: Twitter, label: "Twitter" },
                { href: "https://github.com",  icon: Github,  label: "GitHub" },
                { href: "https://linkedin.com", icon: Linkedin, label: "LinkedIn" },
              ].map(({ href, icon: Icon, label }) => (
                <a key={label} href={href} target="_blank" rel="noopener noreferrer" aria-label={label}
                  className="w-9 h-9 rounded-xl border border-white/8 bg-white/4 flex items-center justify-center text-white/35 hover:text-white/70 hover:border-white/15 transition-all"
                  data-testid={`link-${label.toLowerCase()}`}>
                  <Icon size={14} />
                </a>
              ))}
            </div>
          </div>

          <div>
            <h4 className="text-white/50 text-[11px] font-mono uppercase tracking-widest mb-6">Platform</h4>
            <ul className="space-y-3 text-sm text-white/28 font-light">
              <li><Link href="/dashboard" className="hover:text-white/60 transition-colors">Mission Control</Link></li>
              <li><a href="#features" className="hover:text-white/60 transition-colors">Features</a></li>
              <li><a href="#data" className="hover:text-white/60 transition-colors">Data Sources</a></li>
              <li><a href="#dashboard" className="hover:text-white/60 transition-colors">Interface Preview</a></li>
            </ul>
          </div>

          <div>
            <h4 className="text-white/50 text-[11px] font-mono uppercase tracking-widest mb-6">Contact</h4>
            <ul className="space-y-5 text-sm text-white/28 font-light">
              <li className="flex items-start gap-3">
                <Mail size={13} className="text-white/25 mt-0.5 shrink-0" />
                <div>
                  <p className="text-white/35 text-[10px] font-mono uppercase tracking-wider mb-1">Email</p>
                  <a href="mailto:research@swews.space" className="hover:text-white/60 transition-colors" data-testid="link-email">
                    research@swews.space
                  </a>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Phone size={13} className="text-white/25 mt-0.5 shrink-0" />
                <div>
                  <p className="text-white/35 text-[10px] font-mono uppercase tracking-wider mb-1">Operations</p>
                  <a href="tel:+14155550182" className="hover:text-white/60 transition-colors font-mono text-xs" data-testid="link-phone">
                    +1 (415) 555-0182
                  </a>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <Globe size={13} className="text-white/25 mt-0.5 shrink-0" />
                <div>
                  <p className="text-white/35 text-[10px] font-mono uppercase tracking-wider mb-1">Organization</p>
                  <span>SWEWS Research Labs</span>
                </div>
              </li>
            </ul>
          </div>
        </div>

        <div className="pt-8 border-t border-white/6 flex flex-col md:flex-row items-center justify-between gap-4 text-[11px] text-white/20 font-mono">
          <p>&copy; {new Date().getFullYear()} SWEWS Research Labs. All rights reserved.</p>
          <div className="flex items-center gap-5">
            <span>Model v2.4.1</span>
            <span className="w-px h-3 bg-white/10" />
            <span>NOAA GOES-16/18</span>
            <span className="w-px h-3 bg-white/10" />
            <span>All systems operational</span>
          </div>
        </div>
      </div>
    </footer>
  );
}

/* ─── Page ───────────────────────────────────────────────────────────────── */
export default function Landing() {
  return (
    <div className="min-h-screen bg-[#05080f] text-foreground">
      <NavBar />
      <HeroSection />
      <FeaturesSection />
      <DashboardPreview />
      <DataSourcesSection />
      <Footer />
    </div>
  );
}
