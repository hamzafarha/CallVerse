import {
  Avatar,
  Card,
  ORDER_STATUS,
  PERSONA_COLOR,
  Skeleton,
  Stagger,
  StaggerItem,
  dateLabel,
  humanize,
  motion,
  num,
  useApi,
} from "@callverse/shared";
import { CalendarClock, Copy, CreditCard, History, MessageCircle, Package, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CustomerCard } from "../components/CustomerCard";
import { OrderTimeline } from "../components/OrderTimeline";
import { useCustomer } from "../customer";

export default function AccountPage() {
  const { contactId } = useParams();
  const { customer } = useCustomer();
  if (!contactId) return customer ? <Navigate to={`/account/${customer.contact_id}`} replace /> : <Picker />;
  return <Account contactId={contactId} />;
}

function Picker() {
  const customers = useApi<any[]>("/api/portal/customers");
  const { setCustomer } = useCustomer();
  const navigate = useNavigate();
  return (
    <div>
      <h1 className="font-display text-4xl font-semibold text-ink">Sign in as a demo customer</h1>
      <p className="mt-2 max-w-2xl text-ink2">No password: pick one of the real (anonymised) customers of the twin.</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(customers.data ?? []).map((c, i) => (
          <CustomerCard
            key={c.contact_id}
            index={i}
            customer={c}
            onSelect={() => {
              setCustomer({ contact_id: c.contact_id, name: c.name });
              navigate(`/account/${c.contact_id}`);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function Account({ contactId }: { contactId: string }) {
  const { data, error } = useApi<any>(`/api/portal/customers/${contactId}`);
  const { customer, setCustomer } = useCustomer();
  useEffect(() => {
    if (data && customer?.contact_id !== data.contact_id) setCustomer({ contact_id: data.contact_id, name: data.name });
  }, [data, customer, setCustomer]);

  if (error) return <p className="text-bad">{error}</p>;
  if (!data)
    return (
      <div className="space-y-6">
        <Skeleton className="h-24" />
        <Skeleton className="h-72" />
      </div>
    );
  const order = data.order;
  const status = ORDER_STATUS[order.status_at_contact] ?? { label: humanize(order.status_at_contact), color: "var(--series-1)" };
  const late = Number(order.days_past_estimate) > 0 && order.status_at_contact !== "delivered";
  const copy = () => {
    navigator.clipboard?.writeText(order.order_id);
    toast.success("Order number copied");
  };

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center gap-4">
        <Avatar name={data.name} size={64} />
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink">Welcome back, {data.name.split(" ")[0]}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            {data.city}, {data.state}
            <span className="chip py-0.5 text-[11px]">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: PERSONA_COLOR[data.persona] }} /> demo persona: {data.persona}
            </span>
            {data.is_repeat_contact && <span className="chip py-0.5 text-[11px]">repeat contact</span>}
          </div>
        </div>
        <div className="glass ml-auto flex items-center gap-2 rounded-2xl px-4 py-2 text-xs text-ink2">
          <CalendarClock size={15} className="text-brand" />
          Twin clock: <b className="text-ink">{dateLabel(data.contact_timestamp, true)}</b>
        </div>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card
          title={
            <span className="flex items-center gap-2">
              <Package size={16} className="text-brand" /> Your order
            </span>
          }
          subtitle={
            <button onClick={copy} className="inline-flex items-center gap-1 font-mono hover:text-ink">
              #{order.order_id.slice(0, 12)}… <Copy size={11} />
            </button>
          }
          action={
            <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ color: status.color, background: `color-mix(in srgb, ${status.color} 12%, transparent)` }}>
              {status.label}
            </span>
          }
        >
          <div className="overflow-x-auto pb-2">
            <div className="min-w-[440px]">
              <OrderTimeline steps={data.timeline} />
            </div>
          </div>
          {late && (
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.8 }}
              className="mt-5 rounded-xl border border-[color-mix(in_srgb,var(--critical)_30%,transparent)] bg-[color-mix(in_srgb,var(--critical)_7%,transparent)] px-4 py-3 text-sm text-ink"
            >
              Your delivery is <b>{order.days_past_estimate} days</b> past the estimated date. Our advisor can check the
              tracking and open an investigation with the carrier.
            </motion.div>
          )}
          <Stagger className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            {[
              { label: "Category", value: humanize(order.category) },
              { label: "Order value", value: `R$ ${num(order.value, 2)}` },
              { label: "Items", value: num(order.items, 0) },
              { label: "Payment", value: humanize(order.payment) },
              { label: "Ordered on", value: dateLabel(order.purchased_at) },
              { label: "Estimated delivery", value: dateLabel(order.estimated_delivery) },
            ].map((item) => (
              <StaggerItem key={item.label} className="rounded-xl bg-raised p-3">
                <div className="text-[11px] uppercase tracking-wide text-muted">{item.label}</div>
                <div className="mt-0.5 text-sm font-medium capitalize text-ink">{item.value}</div>
              </StaggerItem>
            ))}
          </Stagger>
        </Card>

        <div className="space-y-6">
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card ring-gradient overflow-hidden p-6">
            <div className="pointer-events-none absolute -right-12 -top-12 h-40 w-40 rounded-full opacity-25 blur-2xl gradient-brand" />
            <Sparkles className="text-brand" />
            <div className="mt-3 text-lg font-semibold text-ink">Need help with this order?</div>
            <p className="mt-1 text-sm text-ink2">You wrote to us:</p>
            <p className="mt-2 rounded-xl bg-raised p-3 text-sm italic text-ink">“{data.opening_message}”</p>
            <Link to={`/chat/${data.contact_id}`} className="btn btn-primary mt-4 w-full py-3">
              <MessageCircle size={16} /> Chat with an advisor
            </Link>
            <div className="mt-3 flex items-center gap-2 text-[11px] text-muted">
              <CreditCard size={12} /> We never ask for card details in chat.
            </div>
          </motion.div>
          <Card
            title={
              <span className="flex items-center gap-2">
                <History size={15} className="text-brand" /> Previous contacts
              </span>
            }
          >
            {data.previous_contacts.length ? (
              <div className="space-y-3">
                {data.previous_contacts.map((c: any) => (
                  <div key={c.contact_id} className="rounded-xl border border-line p-3">
                    <div className="flex justify-between text-[11px] text-muted">
                      <span>{humanize(c.intent)}</span>
                      <span>{dateLabel(c.contact_timestamp)}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-ink2">{c.message_text}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">First time you contact us. Welcome!</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
