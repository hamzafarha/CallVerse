/**
 * "Create a new customer" page: instead of picking an existing customer, the visitor creates one.
 *
 * - Who: a name and a persona (how patient the customer is).
 * - What: the problem (one of the 17 order-linked intents) and the first message (a real example to start).
 * - Which order, two options:
 *   - a REAL Olist order that was in that situation (CallVerse picks it, with the day the customer wrote);
 *   - an INVENTED order typed here, saved in the database like any order.
 * The right column previews what the advisor's tools will see on the day the customer writes.
 */
import { Avatar, Card, ErrorBox, GROUP_LABEL, PageHeader, PERSONA_COLOR, Segmented, Skeleton, clsx, humanize, motion, postJson, useApi } from "@callverse/shared";
import { AlertTriangle, CalendarClock, Database, MessageCircle, Package, UserPlus, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useCustomer } from "../customer";

type Persona = "impatient" | "normal" | "patient";
type Source = "real" | "invented";
type Progress = "processing" | "shipped" | "delivered" | "canceled";

const PERSONA_TEXT: Record<Persona, string> = {
  impatient: "short messages, little patience (leaves sooner)",
  normal: "polite and direct",
  patient: "calm, friendly, gives details",
};
const PROGRESS_LABEL: Record<Progress, string> = {
  processing: "Not shipped yet",
  shipped: "On the way",
  delivered: "Delivered",
  canceled: "Canceled",
};
const PAYMENT_LABEL: Record<string, string> = {
  credit_card: "Credit card",
  boleto: "Boleto (bank slip)",
  debit_card: "Debit card",
  voucher: "Voucher",
};
const INVESTIGATION_AFTER_DAYS = 7; // configs/data.yaml: a parcel this late gets a carrier investigation

// A default invented order: shipped, due on 16 May 2018, the customer writes 8 days later.
const DEFAULT_ORDER = {
  category: "toys",
  value_brl: 129.9,
  items: 1,
  payment_type: "credit_card",
  city: "Sao Paulo",
  state: "SP",
  purchased_at: "2018-05-02",
  estimated_delivery: "2018-05-16",
  progress: "shipped" as Progress,
  shipped_at: "2018-05-04",
  delivered_at: "2018-05-14",
  contact_at: "2018-05-24",
};
type OrderForm = typeof DEFAULT_ORDER;

function days(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / 864e5);
}

/** The order status the tools will see on the contact day (the same rule as data/tickets.py). */
function statusOn(order: OrderForm): string {
  if (order.progress === "canceled") return "canceled";
  if (order.progress === "delivered" && order.delivered_at <= order.contact_at) return "delivered";
  if (order.progress !== "processing" && order.shipped_at <= order.contact_at) return "shipped";
  return order.purchased_at <= order.contact_at ? "approved" : "created";
}

/** First rule an invented order breaks (the server checks the same rules), or null. */
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

export default function NewCustomerPage() {
  const options = useApi<any>("/api/portal/new-customer-options");
  const { setCustomer } = useCustomer();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [persona, setPersona] = useState<Persona>("normal");
  const [intent, setIntent] = useState("track_order");
  const [message, setMessage] = useState("");
  const [messageEdited, setMessageEdited] = useState(false);
  const [source, setSource] = useState<Source>("real");
  const [order, setOrder] = useState<OrderForm>(DEFAULT_ORDER);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const problems: any[] = options.data?.problems ?? [];
  const problem = problems.find((p) => p.intent === intent);
  // The first message follows the chosen problem (a real customer message) until the visitor edits it.
  useEffect(() => {
    if (!messageEdited && problem) setMessage(problem.example);
  }, [problem, messageEdited]);

  const set = <K extends keyof OrderForm>(key: K, value: OrderForm[K]) => setOrder((o) => ({ ...o, [key]: value }));
  const first = options.data?.dates.first ?? "2017-01-11";
  const last = options.data?.dates.last ?? "2018-08-31";
  const problemText = source === "invented" ? orderProblem(order, first, last) : null;
  const blocked = !name.trim() ? "Give the customer a name." : problemText;
  const status = useMemo(() => statusOn(order), [order]);
  const late = days(order.estimated_delivery, order.contact_at);
  // Problems grouped like the twin's four problem families.
  const groups = useMemo(() => {
    const byGroup: Record<string, any[]> = {};
    problems.forEach((p) => (byGroup[p.group] ??= []).push(p));
    return byGroup;
  }, [problems]);

  const create = async (then: "account" | "chat") => {
    if (blocked) return;
    setSaving(true);
    setError(null);
    try {
      const shipped = order.progress === "shipped" || order.progress === "delivered";
      const card = await postJson("/api/portal/customers", {
        name: name.trim(),
        persona,
        intent,
        message: message.trim() || null,
        order_source: source,
        order:
          source === "invented"
            ? {
                ...order,
                value_brl: Number(order.value_brl),
                items: Number(order.items),
                shipped_at: shipped ? order.shipped_at : null,
                delivered_at: order.progress === "delivered" ? order.delivered_at : null,
              }
            : null,
      });
      setCustomer({ contact_id: card.contact_id, name: card.name });
      toast.success(`${card.name} created (${card.contact_id})`);
      navigate(then === "chat" ? `/chat/${card.contact_id}` : `/account/${card.contact_id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (options.error) return <ErrorBox error={options.error} />;
  if (!options.data) return <Skeleton className="h-[520px]" />;

  return (
    <div>
      <PageHeader
        tag="Demo"
        title="Create a new customer"
        subtitle="Instead of picking an existing customer: choose a name, a problem and an order. The four agents then treat this customer like any other."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          {/* 1. Who */}
          <Card title="1. Who is the customer?" icon={<UserPlus size={16} />}>
            <label className="label" htmlFor="nc-name">Name</label>
            <input id="nc-name" className="field" placeholder="e.g. Amira Ben Salah" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="label mb-0">Persona</span>
              <Segmented
                id="nc-persona"
                size="sm"
                value={persona}
                onChange={setPersona}
                options={[
                  { value: "impatient", label: "Impatient" },
                  { value: "normal", label: "Normal" },
                  { value: "patient", label: "Patient" },
                ]}
              />
              <span className="text-xs text-muted">{PERSONA_TEXT[persona]}</span>
            </div>
          </Card>

          {/* 2. What */}
          <Card title="2. What is the problem?" icon={<MessageCircle size={16} />}>
            <label className="label" htmlFor="nc-problem">Problem</label>
            <select id="nc-problem" className="field" value={intent} onChange={(e) => setIntent(e.target.value)}>
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
            <div className="mt-4 flex items-end justify-between gap-2">
              <label className="label mb-0" htmlFor="nc-message">First message</label>
              {messageEdited && problem && (
                <button className="text-xs font-medium text-brand hover:underline" onClick={() => setMessageEdited(false)}>
                  Use a real example again
                </button>
              )}
            </div>
            <textarea
              id="nc-message"
              rows={3}
              maxLength={500}
              className="field mt-1.5 resize-none"
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                setMessageEdited(true);
              }}
            />
            <p className="mt-1.5 text-xs text-muted">Pre-filled with a real customer message (Bitext) for this problem. Change it if you want.</p>
          </Card>

          {/* 3. Which order */}
          <Card
            title="3. Which order?"
            icon={<Package size={16} />}
            action={
              <Segmented
                id="nc-source"
                size="sm"
                value={source}
                onChange={setSource}
                options={[
                  { value: "real", label: <><Database size={12} /> Real order</> },
                  { value: "invented", label: <><Wand2 size={12} /> I invent it</> },
                ]}
              />
            }
          >
            {source === "real" ? (
              <div className="flex gap-3 rounded-xl bg-raised p-4 text-sm text-ink2">
                <Database size={18} className="mt-0.5 shrink-0 text-brand" />
                <p>
                  CallVerse picks a <b className="text-ink">real Olist order</b> where this problem really happened, and the day that customer
                  wrote. Every tool, the rules engine and the quality review then work on real data.
                </p>
              </div>
            ) : (
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Category">
                    <select className="field" value={order.category} onChange={(e) => set("category", e.target.value)}>
                      {(options.data.categories as string[]).map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Order value (R$)">
                    <input className="field" type="number" min={1} max={20000} step={0.01} value={order.value_brl} onChange={(e) => set("value_brl", Number(e.target.value))} />
                  </Field>
                  <Field label="Items">
                    <input className="field" type="number" min={1} max={20} value={order.items} onChange={(e) => set("items", Number(e.target.value))} />
                  </Field>
                  <Field label="Payment">
                    <select className="field" value={order.payment_type} onChange={(e) => set("payment_type", e.target.value)}>
                      {(options.data.payment_types as string[]).map((p) => (
                        <option key={p} value={p}>
                          {PAYMENT_LABEL[p] ?? p}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="City">
                    <input className="field" maxLength={60} value={order.city} onChange={(e) => set("city", e.target.value)} />
                  </Field>
                  <Field label="State">
                    <select className="field" value={order.state} onChange={(e) => set("state", e.target.value)}>
                      {(options.data.states as string[]).map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="label mb-0">How far did it get?</span>
                  <Segmented
                    id="nc-progress"
                    size="sm"
                    value={order.progress}
                    onChange={(v) => set("progress", v)}
                    options={(Object.keys(PROGRESS_LABEL) as Progress[]).map((p) => ({ value: p, label: PROGRESS_LABEL[p] }))}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label="Bought on">
                    <input className="field" type="date" min="2016-09-01" max={last} value={order.purchased_at} onChange={(e) => set("purchased_at", e.target.value)} />
                  </Field>
                  <Field label="Estimated delivery">
                    <input className="field" type="date" min="2016-09-01" max="2018-12-31" value={order.estimated_delivery} onChange={(e) => set("estimated_delivery", e.target.value)} />
                  </Field>
                  {(order.progress === "shipped" || order.progress === "delivered") && (
                    <Field label="Shipped on">
                      <input className="field" type="date" min="2016-09-01" max={last} value={order.shipped_at} onChange={(e) => set("shipped_at", e.target.value)} />
                    </Field>
                  )}
                  {order.progress === "delivered" && (
                    <Field label="Delivered on">
                      <input className="field" type="date" min="2016-09-01" max={last} value={order.delivered_at} onChange={(e) => set("delivered_at", e.target.value)} />
                    </Field>
                  )}
                  <Field label="The customer writes on">
                    <input className="field" type="date" min={first} max={last} value={order.contact_at} onChange={(e) => set("contact_at", e.target.value)} />
                  </Field>
                </div>
                <p className="text-xs text-muted">
                  Saved in the database as a new order, so the advisor's tools find it like any other. Dates stay between {first} and {last}:
                  the twin replays those days (forecast, staffing and waiting times).
                </p>
              </motion.div>
            )}
          </Card>
        </div>

        {/* Preview and buttons */}
        <div className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="card ring-gradient p-5">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-muted">What the agents will see</div>
            <div className="flex items-center gap-3">
              <Avatar name={name.trim() || "New customer"} size={44} />
              <div className="min-w-0">
                <div className="truncate font-semibold text-ink">{name.trim() || "New customer"}</div>
                <div className="flex items-center gap-1.5 text-xs text-muted">
                  <span className="h-2 w-2 rounded-full" style={{ background: PERSONA_COLOR[persona] }} /> {persona} persona
                </div>
              </div>
            </div>
            <div className="mt-4 text-sm font-medium text-ink">{problem?.label}</div>
            <p className="mt-1 line-clamp-3 text-xs italic text-ink2">“{message || "…"}”</p>
            <div className="mt-4 rounded-xl bg-raised p-3 text-xs text-ink2">
              {source === "real" ? (
                <span>A real order in this situation is attached when you create the customer.</span>
              ) : (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5 font-medium text-ink">
                    <CalendarClock size={13} className="text-brand" /> On {order.contact_at}:
                  </div>
                  <div>
                    Order status <b className="text-ink">{status}</b>
                    {status !== "delivered" && status !== "canceled" && (late > 0 ? `, ${late} days past the estimated date` : ", still on time")}.
                  </div>
                  {status === "shipped" && late > INVESTIGATION_AFTER_DAYS && <div>The rules engine will open a carrier investigation.</div>}
                </div>
              )}
            </div>
            {blocked && (
              <div className="mt-3 flex gap-2 rounded-xl p-3 text-xs text-ink" style={{ background: "color-mix(in srgb, var(--warning) 14%, transparent)" }}>
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-warn" /> {blocked}
              </div>
            )}
            {error && <div className="mt-3 rounded-xl p-3 text-xs text-bad" style={{ background: "color-mix(in srgb, var(--critical) 10%, transparent)" }}>{error}</div>}
            <button className="btn btn-primary mt-4 w-full py-3" disabled={!!blocked || saving} onClick={() => create("chat")}>
              <MessageCircle size={16} /> {saving ? "Creating…" : "Create and start a chat"}
            </button>
            <button className={clsx("btn btn-ghost mt-2 w-full")} disabled={!!blocked || saving} onClick={() => create("account")}>
              <Package size={15} /> Create and see the order
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** A labelled form field. */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
