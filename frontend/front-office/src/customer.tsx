import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** The demo customer the visitor "signed in" as (a real contact of the twin). */
export interface DemoCustomer {
  contact_id: string;
  name: string;
}

const KEY = "callverse-demo-customer";
const Context = createContext<{ customer: DemoCustomer | null; setCustomer: (c: DemoCustomer | null) => void }>({
  customer: null,
  setCustomer: () => undefined,
});

function read(): DemoCustomer | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as DemoCustomer) : null;
  } catch {
    return null;
  }
}

export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customer, setCustomer] = useState<DemoCustomer | null>(read);
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

export const useCustomer = () => useContext(Context);
