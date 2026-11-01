import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
import { Search, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";

export interface PaletteItem {
  id: string;
  label: string;
  group: string;
  hint?: string;
  icon?: LucideIcon;
  keywords?: string[];
  run: () => void;
}

/** ⌘K / Ctrl+K command palette: jump to any page or action. */
export function CommandPalette({ items }: { items: PaletteItem[] }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((o) => !o);
      }
      if (event.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("callverse:palette", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("callverse:palette", onOpen);
    };
  }, []);
  const groups = Array.from(new Set(items.map((i) => i.group)));
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[14vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -6 }}
            transition={{ type: "spring", bounce: 0.25, duration: 0.4 }}
            className="card w-full max-w-xl overflow-hidden p-0 shadow-lift"
            onClick={(e) => e.stopPropagation()}
          >
            <Command label="Command palette" loop>
              <div className="flex items-center gap-3 border-b border-line px-4">
                <Search size={17} className="text-muted" />
                <Command.Input
                  autoFocus
                  placeholder="Jump to a page or run an action…"
                  className="h-14 w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-muted"
                />
                <span className="kbd">Esc</span>
              </div>
              <Command.List className="max-h-[360px] overflow-y-auto p-2">
                <Command.Empty className="px-3 py-8 text-center text-sm text-muted">Nothing found.</Command.Empty>
                {groups.map((group) => (
                  <Command.Group
                    key={group}
                    heading={group}
                    className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted"
                  >
                    {items
                      .filter((i) => i.group === group)
                      .map((item) => {
                        const Icon = item.icon;
                        return (
                          <Command.Item
                            key={item.id}
                            value={`${item.label} ${item.keywords?.join(" ") ?? ""}`}
                            onSelect={() => {
                              setOpen(false);
                              item.run();
                            }}
                            className="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-ink2 data-[selected=true]:bg-raised data-[selected=true]:text-ink"
                          >
                            {Icon && (
                              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sunken text-brand">
                                <Icon size={15} />
                              </span>
                            )}
                            <span className="flex-1">{item.label}</span>
                            {item.hint && <span className="text-xs text-muted">{item.hint}</span>}
                          </Command.Item>
                        );
                      })}
                  </Command.Group>
                ))}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Button that opens the palette (for the top bar). */
export function PaletteButton() {
  const mac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);
  return (
    <button
      onClick={() => window.dispatchEvent(new Event("callverse:palette"))}
      className="btn btn-ghost hidden min-w-[220px] justify-between text-muted md:inline-flex"
    >
      <span className="inline-flex items-center gap-2">
        <Search size={15} /> Search…
      </span>
      <span className="flex gap-1">
        <span className="kbd">{mac ? "⌘" : "Ctrl"}</span>
        <span className="kbd">K</span>
      </span>
    </button>
  );
}
