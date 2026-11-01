import {
  APP_URLS,
  Aurora,
  Avatar,
  CommandPalette,
  Logo,
  ThemeToggle,
  clsx,
  motion,
  useTheme,
  type PaletteItem,
} from "@callverse/shared";
import { AnimatePresence } from "framer-motion";
import {
  BookOpen,
  ExternalLink,
  Headset,
  Home,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircle,
  Package,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";
import { useCustomer } from "../customer";

const NAV = [
  { to: "/", label: "Home", icon: Home },
  { to: "/help", label: "Help centre", icon: BookOpen },
  { to: "/account", label: "My orders", icon: Package },
  { to: "/chat", label: "Live chat", icon: MessageCircle },
];

export default function Shell({ children }: { children: ReactNode }) {
  const { dark, toggle, theme } = useTheme("light", "callverse-theme-front");
  const { customer, setCustomer } = useCustomer();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const desk = location.pathname.startsWith("/desk");

  const palette: PaletteItem[] = [
    ...NAV.map((n) => ({ id: n.to, label: n.label, group: "Customer", icon: n.icon, run: () => navigate(n.to) })),
    { id: "desk", label: "Advisor desk", group: "Staff", icon: Headset, run: () => navigate("/desk") },
    { id: "back", label: "Open the control room (back office)", group: "Staff", icon: LayoutDashboard, run: () => window.open(APP_URLS.back, "_blank") },
    { id: "theme", label: dark ? "Switch to light theme" : "Switch to dark theme", group: "Preferences", run: toggle },
  ];

  const link = (to: string, label: string, Icon: any) => (
    <NavLink
      key={to}
      to={to}
      end={to === "/"}
      onClick={() => setOpen(false)}
      className={({ isActive }) =>
        clsx("relative rounded-xl px-3 py-2 text-sm font-medium transition-colors", isActive ? "text-ink" : "text-muted hover:text-ink")
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span layoutId="front-nav" className="absolute inset-0 rounded-xl bg-raised" transition={{ type: "spring", bounce: 0.25, duration: 0.5 }} />
          )}
          <span className="relative z-10 inline-flex items-center gap-2">
            <Icon size={15} /> {label}
          </span>
        </>
      )}
    </NavLink>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <Aurora intensity={dark ? 0.9 : 0.7} />
      <Toaster position="bottom-right" theme={theme} richColors closeButton />
      <CommandPalette items={palette} />
      <header className="glass sticky top-0 z-40 border-x-0 border-t-0">
        <div className={clsx("mx-auto flex h-16 items-center gap-4 px-4 sm:px-6", desk ? "max-w-none" : "max-w-7xl")}>
          <Link to="/" className="shrink-0">
            <Logo product="Care" tagline="Help centre · demo store" />
          </Link>
          <nav className="ml-4 hidden items-center gap-1 lg:flex">{NAV.map((n) => link(n.to, n.label, n.icon))}</nav>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden items-center gap-1 rounded-xl border border-dashed border-line px-1 py-1 md:flex">
              <span className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted">Staff</span>
              {link("/desk", "Advisor desk", Headset)}
              <a href={APP_URLS.back} target="_blank" rel="noreferrer" className="rounded-xl px-3 py-2 text-sm font-medium text-muted hover:text-ink">
                <span className="inline-flex items-center gap-2">
                  <LayoutDashboard size={15} /> Control room <ExternalLink size={12} />
                </span>
              </a>
            </div>
            {customer && (
              <div className="hidden items-center gap-2 rounded-xl border border-line bg-surface py-1 pl-1 pr-2 sm:flex">
                <Avatar name={customer.name} size={28} />
                <span className="text-sm font-medium text-ink">{customer.name}</span>
                <button onClick={() => { setCustomer(null); navigate("/"); }} className="text-muted hover:text-ink" title="Sign out of the demo customer">
                  <LogOut size={14} />
                </button>
              </div>
            )}
            <ThemeToggle dark={dark} toggle={toggle} />
            <button className="btn btn-ghost btn-icon lg:hidden" onClick={() => setOpen(!open)} aria-label="Menu">
              {open ? <X size={16} /> : <Menu size={16} />}
            </button>
          </div>
        </div>
        <AnimatePresence>
          {open && (
            <motion.nav
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-line lg:hidden"
            >
              <div className="flex flex-col gap-1 p-3">
                {NAV.map((n) => link(n.to, n.label, n.icon))}
                {link("/desk", "Advisor desk (staff)", Headset)}
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>
      <main className={clsx("flex-1", desk ? "" : "mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:py-10")}>{children}</main>
      {!desk && (
        <footer className="border-t border-line">
          <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-8 text-xs text-muted sm:px-6 md:flex-row md:items-center md:justify-between">
            <Logo product="Care" />
            <p className="max-w-2xl leading-relaxed">
              Demo help centre of the CallVerse digital twin. Orders are real, anonymised Olist orders; contacts are
              synthetic. The AI advisor runs locally: SmolLM3-3B (Hugging Face) writes, a rules engine decides, bge-m3
              retrieves the policies and an IBM Granite judge reviews every chat.
            </p>
          </div>
        </footer>
      )}
    </div>
  );
}
