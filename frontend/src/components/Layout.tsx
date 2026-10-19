import {
  Activity,
  Bot,
  ClipboardCheck,
  Database,
  FlaskConical,
  Headphones,
  LayoutDashboard,
  Menu,
  Moon,
  Server,
  Sun,
  TrendingUp,
  Users,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, color: "var(--brand)" },
  { to: "/data", label: "Data layer", icon: Database, color: "var(--layer-data)" },
  { to: "/forecast", label: "Forecast", icon: TrendingUp, color: "var(--layer-sim)" },
  { to: "/twin", label: "Digital twin", icon: Activity, color: "var(--layer-sim)" },
  { to: "/workforce", label: "Workforce agent", icon: Users, color: "var(--layer-agents)" },
  { to: "/agents", label: "Agent playground", icon: Bot, color: "var(--layer-agents)" },
  { to: "/quality", label: "Quality & labeling", icon: ClipboardCheck, color: "var(--layer-agents)" },
  { to: "/evaluation", label: "Evaluation", icon: FlaskConical, color: "var(--layer-eval)" },
  { to: "/mlops", label: "Serving & MLOps", icon: Server, color: "var(--layer-serve)" },
];

function useTheme() {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem("callverse-theme") ?? "";
    } catch {
      return "";
    }
  });
  useEffect(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
    try {
      localStorage.setItem("callverse-theme", theme);
    } catch {
      /* private mode: theme just isn't remembered */
    }
  }, [theme]);
  const dark =
    theme === "dark" || (!theme && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  return { dark, toggle: () => setTheme(dark ? "light" : "dark") };
}

export default function Layout({ children }: { children: ReactNode }) {
  const { dark, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-page">
      <aside
        className={`fixed inset-y-0 left-0 z-30 w-64 border-r border-line bg-surface p-4 transition-transform lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-center gap-3 px-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "var(--brand)" }}>
            <Headphones className="text-white" size={22} />
          </div>
          <div>
            <div className="text-lg font-bold tracking-tight text-ink">CallVerse</div>
            <div className="text-[11px] text-muted">Customer service digital twin</div>
          </div>
        </div>
        <nav className="space-y-1">
          {NAV.map(({ to, label, icon: Icon, color }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  isActive ? "bg-raised font-semibold text-ink shadow-sm" : "text-ink2 hover:bg-raised"
                }`
              }
            >
              <Icon size={17} style={{ color }} />
              {label}
            </NavLink>
          ))}
        </nav>
        <button onClick={toggle} className="btn btn-ghost absolute bottom-4 left-4 right-4 justify-center">
          {dark ? <Sun size={16} /> : <Moon size={16} />} {dark ? "Light mode" : "Dark mode"}
        </button>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-3 backdrop-blur lg:hidden">
          <button onClick={() => setOpen(!open)} className="btn btn-ghost px-2" aria-label="Menu">
            <Menu size={18} />
          </button>
          <span className="font-semibold text-ink">CallVerse</span>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
