/**
 * Remembers which demo customer the visitor "signed in" as, for every page (a React context), and keeps it in
 * the browser (localStorage) so a page reload does not forget it. There is no real login: it is a demo.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** The demo customer the visitor "signed in" as (a real contact of the twin). */
export interface DemoCustomer {
  contact_id: string;
  name: string;
}

// localStorage key, and the context with its default value (nobody signed in).
const KEY = "callverse-demo-customer";
const Context = createContext<{ customer: DemoCustomer | null; setCustomer: (c: DemoCustomer | null) => void }>({
  customer: null,
  setCustomer: () => undefined,
});

/**
 * Read the saved customer: null if there is none or if the browser blocks storage.
 */
function read(): DemoCustomer | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as DemoCustomer) : null;
  } catch {
    return null;
  }
}

/**
 * Wraps the app (see App.tsx) so every page can read and change the customer.
 */
export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customer, setCustomer] = useState<DemoCustomer | null>(read);
  // Save every change (or remove the key when the visitor signs out).
  useEffect(() => {
    try {
      if (customer) localStorage.setItem(KEY, JSON.stringify(customer));
      else localStorage.removeItem(KEY);
    } catch {
      /* not remembered */
    }
  }, [customer]);
  return <Context.Provider value={{ customer, setCustomer }}>{children}</Context.Provider>;
}

// Hook used by the pages: const { customer, setCustomer } = useCustomer();
export const useCustomer = () => useContext(Context);
