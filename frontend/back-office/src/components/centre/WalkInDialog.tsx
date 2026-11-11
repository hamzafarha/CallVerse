/**
 * "Who walks in?": the chooser behind the centre's "A customer walks in" button.
 *
 * - Random: a random customer from the history (a real contact message and its real Olist order);
 * - A customer: the portal's demo customers (one per main problem) and the new customers created before;
 * - New customer: a name, a persona, one of the 17 problems, a first message (a real customer's message for
 *   that problem, editable), and either a real Olist order (picked by the server for this problem) or a new
 *   order typed here. It uses the customer portal's own endpoints (/api/portal/...), with the same rules as
 *   the portal's "new customer" form, so the customer also appears on the portal and the advisor desk.
 *
 * The Client agent then plays the chosen customer (POST /api/centre/arrivals with its contact id).
 */
import { GROUP_LABEL, ORDER_STATUS, Segmented, clsx, humanize, postJson, useApi } from "@callverse/shared";
import { AnimatePresence, motion } from "framer-motion";
import { DoorOpen, Shuffle, Sparkles, UserPlus, Users, X } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";

type Tab = "random" | "existing" | "new";
type Persona = "impatient" | "normal" | "patient";
type Progress = "processing" | "shipped" | "delivered" | "canceled";

const PAYMENT_LABEL: Record<string, string> = { credit_card: "Credit card", boleto: "Boleto", debit_card: "Debit card", voucher: "Voucher" };
const PROGRESS_LABEL: Record<Progress, string> = { processing: "Not shipped", shipped: "On its way", delivered: "Delivered", canceled: "Canceled" };

// A default new order (the same as the portal's form): shipped, due on 16 May 2018, the customer writes 8 days
// later.
const DEFAULT_ORDER = {
  category: "toys",
  value_brl: 129.9,
  payment_type: "credit_card",
  purchased_at: "2018-05-02",
  estimated_delivery: "2018-05-16",
  progress: "shipped" as Progress,
  shipped_at: "2018-05-04",
  delivered_at: "2018-05-14",
  contact_at: "2018-05-24",
};
type OrderForm = typeof DEFAULT_ORDER;

/** First rule a new order breaks (the server checks the same rules), or null. */
function orderProblem(order: OrderForm, first: string, last: string): string | null {
  if (!(order.value_brl > 0)) return "The order value must be more than 0.";
  if (order.contact_at < first || order.contact_at > last) return `The contact day must be between ${first} and ${last}: the twin replays those days.`;
  if (order.purchased_at > order.contact_at) return "The customer cannot write before buying.";
  if (order.estimated_delivery < order.purchased_at) return "The estimated delivery cannot be before the purchase.";
  if ((order.progress === "shipped" || order.progress === "delivered") && order.shipped_at < order.purchased_at)
    return "The shipping date must come after the purchase.";
  if (order.progress === "delivered" && order.delivered_at < order.shipped_at) return "The delivery date must come after shipping.";
  return null;
}

export function WalkInDialog({
  open,
  onClose,
  onWalkIn,
}: {
  open: boolean;
  onClose: () => void;
  onWalkIn: (contactId: string | null) => Promise<boolean>;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div key="shade" className="fixed inset-0 z-[3000] bg-black/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          {/* Centred by a full-screen flex box (the opening animation's scale would override a CSS translate). */}
          <div key="frame" className="pointer-events-none fixed inset-0 z-[3001] flex items-center justify-center p-4">
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Who walks in?"
              className="pointer-events-auto flex max-h-[88vh] w-[min(700px,100%)] flex-col rounded-3xl border border-line bg-surface shadow-lift"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
            >
              <Chooser onClose={onClose} onWalkIn={onWalkIn} />
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}

function Chooser({ onClose, onWalkIn }: { onClose: () => void; onWalkIn: (contactId: string | null) => Promise<boolean> }) {
  const [tab, setTab] = useState<Tab>("random");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const go = async (contactId: string | null) => {
    setBusy(true);
    const ok = await onWalkIn(contactId);
    setBusy(false);
    if (ok) onClose();
  };
  return (
    <>
      <header className="flex items-center gap-3 border-b border-line px-5 py-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl text-white" style={{ background: "#3b82f6" }}>
          <DoorOpen size={18} />
        </span>
        <div className="flex-1">
          <div className="font-display text-lg font-semibold text-ink">Who walks in?</div>
          <div className="text-xs text-muted">The Client agent plays this customer; the other agents handle the chat as usual.</div>
        </div>
        <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </header>
      <div className="border-b border-line px-5 py-3">
        <Segmented
          id="walk-in-tab"
          value={tab}
          onChange={(value) => {
            setTab(value);
            setError(null);
          }}
          options={[
            { value: "random", label: <><Shuffle size={13} /> Random</> },
            { value: "existing", label: <><Users size={13} /> A customer</> },
            { value: "new", label: <><UserPlus size={13} /> New customer</> },
          ]}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {tab === "random" && (
          <div className="space-y-4 text-sm text-ink2">
            <p>A random customer from the history: a real contact message (Bitext) on a real Olist order, with its real dates and status.</p>
            <button className="btn btn-primary" onClick={() => go(null)} disabled={busy}>
              <DoorOpen size={15} /> Let a random customer walk in
            </button>
          </div>
        )}
        {tab === "existing" && <ExistingCustomers busy={busy} onPick={go} />}
        {tab === "new" && <NewCustomerForm busy={busy} setBusy={setBusy} error={error} setError={setError} onCreated={go} />}
      </div>
    </>
  );
}

/** The portal's demo customers and the new customers created before: pick one, then walk in. */
function ExistingCustomers({ busy, onPick }: { busy: boolean; onPick: (contactId: string) => void }) {
  const demo = useApi<any[]>("/api/portal/customers");
  const created = useApi<any[]>("/api/portal/new-customers");
  const [picked, setPicked] = useState<string | null>(null);
  const cards = [...(created.data ?? []), ...(demo.data ?? [])];
  return (
    <div className="space-y-3">
      {(demo.loading || created.loading) && !cards.length && <p className="text-sm text-muted">Loading the customers…</p>}
      {(demo.error || created.error) && <p className="text-sm" style={{ color: "var(--critical)" }}>{demo.error ?? created.error}</p>}
      <div className="grid gap-2 sm:grid-cols-2">
        {cards.map((card) => {
          const status = ORDER_STATUS[card.order?.status_at_contact]?.label ?? humanize(card.order?.status_at_contact);
          return (
            <button
              key={card.contact_id}
              onClick={() => setPicked(card.contact_id)}
              className={clsx(
                "rounded-2xl border p-3 text-left transition-colors",
                picked === card.contact_id ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "border-line bg-raised hover:border-[var(--baseline)]",
              )}
              aria-pressed={picked === card.contact_id}
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                {card.name}
                {card.is_new && <span className="rounded-full bg-[var(--brand-soft)] px-1.5 text-[10px] font-semibold text-brand">new</span>}
                <span className="ml-auto text-[11px] font-normal text-muted">{humanize(card.intent)}</span>
              </div>
              <div className="mt-1 line-clamp-2 text-xs text-ink2">“{card.opening_message}”</div>
              <div className="mt-1 text-[11px] text-muted">
                {card.order?.category || "order"} · {status}
                {card.order?.value != null ? ` · R$ ${Number(card.order.value).toFixed(2)}` : ""}
              </div>
            </button>
          );
        })}
      </div>
      <button className="btn btn-primary" onClick={() => picked && onPick(picked)} disabled={!picked || busy}>
        <DoorOpen size={15} /> {picked ? "Walk in" : "Choose a customer"}
      </button>
    </div>
  );
}

/** A brand-new customer: problem, first message, and a real Olist order or a new one. */
function NewCustomerForm({
  busy,
  setBusy,
  error,
  setError,
  onCreated,
}: {
  busy: boolean;
  setBusy: (busy: boolean) => void;
  error: string | null;
  setError: (error: string | null) => void;
  onCreated: (contactId: string) => Promise<void>;
}) {
  const options = useApi<any>("/api/portal/new-customer-options");
  const [name, setName] = useState("");
  const [persona, setPersona] = useState<Persona>("normal");
  const [intent, setIntent] = useState("track_order");
  const [message, setMessage] = useState("");
  const [edited, setEdited] = useState(false);
  const [source, setSource] = useState<"real" | "invented">("real");
  const [order, setOrder] = useState<OrderForm>(DEFAULT_ORDER);
  const problems: any[] = options.data?.problems ?? [];
  const problem = problems.find((p) => p.intent === intent);
  // The first message follows the chosen problem (a real customer's message) until you edit it.
  useEffect(() => {
    if (!edited && problem) setMessage(problem.example);
  }, [problem, edited]);
  const groups = useMemo(() => {
    const byGroup: Record<string, any[]> = {};
    problems.forEach((p) => (byGroup[p.group] ??= []).push(p));
    return byGroup;
  }, [problems]);
  const first = options.data?.dates.first ?? "2017-01-11";
  const last = options.data?.dates.last ?? "2018-08-31";
  const set = <K extends keyof OrderForm>(key: K, value: OrderForm[K]) => setOrder((o) => ({ ...o, [key]: value }));
  const blocked = !name.trim() ? "Give the customer a name." : !message.trim() ? "Write the first message." : source === "invented" ? orderProblem(order, first, last) : null;
  const shipped = order.progress === "shipped" || order.progress === "delivered";

  const create = async () => {
    if (blocked) return;
    setBusy(true);
    setError(null);
    try {
      const card = await postJson("/api/portal/customers", {
        name: name.trim(),
        persona,
        intent,
        message: message.trim(),
        order_source: source,
        order:
          source === "invented"
            ? {
                category: order.category,
                value_brl: Number(order.value_brl),
                items: 1,
                payment_type: order.payment_type,
                city: "Sao Paulo",
                state: "SP",
                purchased_at: order.purchased_at,
                estimated_delivery: order.estimated_delivery,
                progress: order.progress,
                shipped_at: shipped ? order.shipped_at : null,
                delivered_at: order.progress === "delivered" ? order.delivered_at : null,
                contact_at: order.contact_at,
              }
            : null,
      });
      setBusy(false);
      await onCreated(card.contact_id);
    } catch (problemMessage) {
      setBusy(false);
      setError(String((problemMessage as Error)?.message ?? problemMessage).replace(/^422\s*/, ""));
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input className="field" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} placeholder="e.g. Amira" />
        </Field>
        <Field label="Persona (how they speak and wait)">
          <Segmented
            id="walk-in-persona"
            size="sm"
            value={persona}
            onChange={setPersona}
            options={[
              { value: "impatient", label: "Impatient" },
              { value: "normal", label: "Normal" },
              { value: "patient", label: "Patient" },
            ]}
          />
        </Field>
      </div>
      <Field label="Problem">
        <select className="field" value={intent} onChange={(e) => setIntent(e.target.value)}>
          {Object.entries(groups).map(([group, list]) => (
            <optgroup key={group} label={GROUP_LABEL[group] ?? humanize(group)}>
              {list.map((p) => (
                <option key={p.intent} value={p.intent}>
                  {p.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </Field>
      <Field label={edited ? "First message (yours)" : "First message (a real customer's message for this problem: edit it if you like)"}>
        <textarea
          className="field min-h-[64px]"
          value={message}
          maxLength={500}
          onChange={(e) => {
            setMessage(e.target.value);
            setEdited(true);
          }}
        />
      </Field>
      <Field label="Order">
        <Segmented
          id="walk-in-order"
          size="sm"
          value={source}
          onChange={setSource}
          options={[
            { value: "real", label: "A real Olist order" },
            { value: "invented", label: <><Sparkles size={12} /> A new order</> },
          ]}
        />
        <p className="mt-1 text-xs text-muted">
          {source === "real"
            ? "The server picks a real Olist order that fits this problem (real dates, status and payment)."
            : "You type the order: the tools will see exactly this order on the contact day."}
        </p>
      </Field>
      {source === "invented" && (
        <div className="grid gap-3 rounded-2xl border border-line bg-raised p-3 sm:grid-cols-3">
          <Field label="Category">
            <select className="field" value={order.category} onChange={(e) => set("category", e.target.value)}>
              {(options.data?.categories ?? [order.category]).map((c: string) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Value (R$)">
            <input className="field" type="number" min={1} max={20000} step={0.01} value={order.value_brl} onChange={(e) => set("value_brl", Number(e.target.value))} />
          </Field>
          <Field label="Payment">
            <select className="field" value={order.payment_type} onChange={(e) => set("payment_type", e.target.value)}>
              {(options.data?.payment_types ?? Object.keys(PAYMENT_LABEL)).map((p: string) => (
                <option key={p} value={p}>
                  {PAYMENT_LABEL[p] ?? humanize(p)}
                </option>
              ))}
            </select>
          </Field>
          <div className="sm:col-span-3">
            <Field label="How far did the order get?">
              <Segmented
                id="walk-in-progress"
                size="sm"
                value={order.progress}
                onChange={(value) => set("progress", value)}
                options={(Object.keys(PROGRESS_LABEL) as Progress[]).map((p) => ({ value: p, label: PROGRESS_LABEL[p] }))}
              />
            </Field>
          </div>
          <Field label="Bought on">
            <input className="field" type="date" min="2016-09-01" max={last} value={order.purchased_at} onChange={(e) => set("purchased_at", e.target.value)} />
          </Field>
          <Field label="Expected delivery">
            <input className="field" type="date" min="2016-09-01" max="2018-12-31" value={order.estimated_delivery} onChange={(e) => set("estimated_delivery", e.target.value)} />
          </Field>
          <Field label="The customer writes on">
            <input className="field" type="date" min={first} max={last} value={order.contact_at} onChange={(e) => set("contact_at", e.target.value)} />
          </Field>
          {shipped && (
            <Field label="Shipped on">
              <input className="field" type="date" min="2016-09-01" max={last} value={order.shipped_at} onChange={(e) => set("shipped_at", e.target.value)} />
            </Field>
          )}
          {order.progress === "delivered" && (
            <Field label="Delivered on">
              <input className="field" type="date" min="2016-09-01" max={last} value={order.delivered_at} onChange={(e) => set("delivered_at", e.target.value)} />
            </Field>
          )}
        </div>
      )}
      {(blocked || error) && (
        <p className="text-xs" style={{ color: error ? "var(--critical)" : "var(--text-muted)" }}>
          {error ?? blocked}
        </p>
      )}
      <button className="btn btn-primary" onClick={create} disabled={!!blocked || busy || options.loading}>
        <UserPlus size={15} /> Create the customer and walk in
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
