import {
  APP_URLS,
  Aurora,
  CommandPalette,
  Logo,
  LogoMark,
  PaletteButton,
  ThemeToggle,
  clsx,
  motion,
  useApi,
  useTheme,
  type PaletteItem,
} from "@callverse/shared";
import {
  Activity,
  Bot,
  ChevronsLeft,
  ClipboardCheck,
  Cpu,
  Database,
  ExternalLink,
  FlaskConical,
  LayoutDashboard,
  Menu,
  Server,
  Store,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export const SECTIONS: { title: string; color: string; items: NavItem[] }[] = [
  { title: "Control room", color: "var(--brand)", items: [{ to: "/", label: "Overview", icon: LayoutDashboard }] },
  { title: "Data layer", color: "var(--layer-data)", items: [{ to: "/data", label: "Data & contracts", icon: Database }] },
  {
    title: "Simulation & forecasting",
    color: "var(--layer-sim)",
    items: [
      { to: "/forecast", label: "Demand forecast", icon: TrendingUp },
      { to: "/twin", label: "Digital twin", icon: Activity },
    ],
  },
  {
    title: "Agents",
    color: "var(--layer-agents)",
    items: [
      { to: "/agents", label: "Agent theater", icon: Bot },
      { to: "/workforce", label: "Workforce agent", icon: Users },
      { to: "/quality", label: "Quality & labeling", icon: ClipboardCheck },
    ],
  },
  { title: "Evaluation", color: "var(--layer-eval)", items: [{ to: "/evaluation", label: "BO / DSO scorecard", icon: FlaskConical }] },
  { title: "Serving & MLOps", color: "var(--layer-serve)", items: [{ to: "/mlops", label: "Models & MLOps", icon: Server }] },
];

function useCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("callverse-sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem("callverse-sidebar", collapsed ? "collapsed" : "open");
    } catch {
      /* not remembered */
    }
  }, [collapsed]);
  return [collapsed, setCollapsed] as const;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { dark, toggle, theme } = useTheme("dark", "callverse-theme-back");
  const [collapsed, setCollapsed] = useCollapsed();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const section = SECTIONS.find((s) => s.items.some((i) => (i.to === "/" ? location.pathname === "/" : location.pathname.startsWith(i.to))));
  const page = section?.items.find((i) => (i.to === "/" ? location.pathname === "/" : location.pathname.startsWith(i.to)));

  const palette: PaletteItem[] = [
    ...SECTIONS.flatMap((s) => s.items.map((i) => ({ id: i.to, label: i.label, group: s.title, icon: i.icon, run: () => navigate(i.to) }))),
    { id: "front", label: "Open the front office (customer portal)", group: "Apps", icon: Store, run: () => window.open(APP_URLS.front, "_blank") },
    { id: "docs", label: "API documentation (Swagger)", group: "Apps", icon: Server, run: () => window.open("/docs", "_blank") },
    { id: "theme", label: dark ? "Switch to light theme" : "Switch to dark theme", group: "Preferences", run: toggle },
  ];

  const width = collapsed ? 76 : 272;
  return (
    <div className="min-h-screen">
      <Aurora intensity={dark ? 0.7 : 0.5} />
      <Toaster position="bottom-right" theme={theme} richColors closeButton />
      <CommandPalette items={palette} />
      <motion.aside
        animate={{ width }}
        transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
        className={clsx(
          "glass fixed inset-y-0 left-0 z-40 flex flex-col border-y-0 border-l-0 px-3 py-4 transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className={clsx("mb-6 flex items-center px-1", collapsed ? "justify-center" : "justify-between")}>
          {collapsed ? <LogoMark /> : <Logo product="Control" tagline="Back office · managers" />}
        </div>
        <nav className="flex-1 space-y-5 overflow-y-auto overflow-x-hidden">
          {SECTIONS.map((s) => (
            <div key={s.title}>
              {!collapsed && (
                <div className="mb-1.5 flex items-center gap-2 px-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} /> {s.title}
                </div>
              )}
              <div className="space-y-0.5">
                {s.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === "/"}
                    onClick={() => setOpen(false)}
                    title={collapsed ? label : undefined}
                    className={({ isActive }) =>
                      clsx(
                        "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                        collapsed && "justify-center",
                        isActive ? "font-semibold text-ink" : "text-ink2 hover:text-ink",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <motion.span
                            layoutId="back-nav"
                            className="absolute inset-0 rounded-xl border border-line bg-surface shadow-soft"
                            transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
                          />
                        )}
                        {isActive && <motion.span layoutId="back-nav-bar" className="absolute left-0 top-2 bottom-2 w-1 rounded-full" style={{ background: s.color }} />}
                        <Icon size={18} className="relative z-10 shrink-0" style={{ color: isActive ? s.color : undefined }} />
                        {!collapsed && <span className="relative z-10 truncate">{label}</span>}
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <SystemCard collapsed={collapsed} />
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="btn btn-ghost mt-3 hidden justify-center lg:inline-flex"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <motion.span animate={{ rotate: collapsed ? 180 : 0 }}>
            <ChevronsLeft size={16} />
          </motion.span>
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
      </motion.aside>

      <div style={{ ["--sidebar" as any]: `${width}px` }} className="transition-[padding] duration-500 lg:pl-[var(--sidebar)]">
        <header className="glass sticky top-0 z-30 border-x-0 border-t-0">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
            <button onClick={() => setOpen(!open)} className="btn btn-ghost btn-icon lg:hidden" aria-label="Menu">
              <Menu size={18} />
            </button>
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <span className="hidden truncate text-muted sm:inline">{section?.title}</span>
              <span className="hidden text-muted sm:inline">/</span>
              <span className="truncate font-semibold text-ink">{page?.label ?? "Overview"}</span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <PaletteButton />
              <a href={APP_URLS.front} target="_blank" rel="noreferrer" className="btn btn-ghost hidden sm:inline-flex">
                <Store size={15} /> Front office <ExternalLink size={12} />
              </a>
              <ThemeToggle dark={dark} toggle={toggle} />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

/** Live status of the local LLMs and the GPU (polled). */
function SystemCard({ collapsed }: { collapsed: boolean }) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((t) => t + 1), 15000);
    return () => window.clearInterval(timer);
  }, []);
  const { data } = useApi<any>(`/api/system?t=${tick}`);
  const llm = data?.llm;
  const gpu = llm?.gpu;
  const loaded = llm ? Object.values(llm.roles).filter((r: any) => r.loaded).length : 0;
  const ok = !!data?.llm_available;
  if (collapsed)
    return (
      <div className="mx-auto mb-1 flex h-10 w-10 items-center justify-center rounded-xl border border-line" title={ok ? "LLMs ready" : "Offline backups"}>
        <span className={ok ? "live-dot" : "h-2 w-2 rounded-full bg-[var(--warning)]"} />
      </div>
    );
  return (
    <div className="rounded-2xl border border-line bg-surface/60 p-3 text-xs">
      <div className="flex items-center gap-2 font-semibold text-ink">
        {ok ? <span className="live-dot" /> : <span className="h-2 w-2 rounded-full bg-[var(--warning)]" />}
        {ok ? "Local LLMs ready" : "Offline backups"}
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-muted">
        <Cpu size={12} /> {gpu ? gpu.name.replace("NVIDIA GeForce ", "").replace(" with Max-Q Design", "") : "no GPU"}
      </div>
      {gpu && (
        <div className="mt-2">
          <div className="h-1.5 overflow-hidden rounded-full bg-sunken">
            <motion.div className="h-full rounded-full gradient-brand" animate={{ width: `${(gpu.used_mb / gpu.total_mb) * 100}%` }} />
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-muted">
            <span>VRAM {(gpu.used_mb / 1024).toFixed(1)} / {(gpu.total_mb / 1024).toFixed(1)} GB</span>
            <span>{loaded} model{loaded === 1 ? "" : "s"} loaded</span>
          </div>
        </div>
      )}
    </div>
  );
}
