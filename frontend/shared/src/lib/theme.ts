import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

function read(key: string): Theme | null {
  try {
    const value = localStorage.getItem(key);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // private mode: the theme just isn't remembered
  }
}

/** Light/dark theme, remembered per app; each app has its own default. */
export function useTheme(defaultTheme: Theme, storageKey: string) {
  const [theme, setTheme] = useState<Theme>(() => read(storageKey) ?? defaultTheme);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(storageKey, theme);
    } catch {
      /* not remembered */
    }
  }, [theme, storageKey]);
  return { theme, dark: theme === "dark", toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}

/** Current value of CSS variables (canvas drawing), refreshed when the theme changes. */
export function useCssVars(names: string[], theme: Theme): Record<string, string> {
  const [values, setValues] = useState<Record<string, string>>({});
  const key = names.join(",");
  useEffect(() => {
    const style = getComputedStyle(document.documentElement);
    setValues(Object.fromEntries(names.map((n) => [n, style.getPropertyValue(n).trim()])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, theme]);
  return values;
}

/** Theme currently applied to <html data-theme>, updated when it changes. */
export function useDocumentTheme(): Theme {
  const read = (): Theme => (document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
  const [theme, setTheme] = useState<Theme>(read);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(read()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}
