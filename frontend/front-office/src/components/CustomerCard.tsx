import { Avatar, ORDER_STATUS, PERSONA_COLOR, Spotlight, humanize, motion } from "@callverse/shared";
import { ArrowRight, MapPin } from "lucide-react";

/** A demo customer (one real contact of the twin) the visitor can sign in as. */
export function CustomerCard({ customer, onSelect, index = 0 }: { customer: any; onSelect: () => void; index?: number }) {
  const status = ORDER_STATUS[customer.order.status_at_contact] ?? { label: humanize(customer.order.status_at_contact), color: "var(--series-1)" };
  const late = Number(customer.order.days_past_estimate) > 0 && customer.order.status_at_contact !== "delivered";
  return (
    <motion.button
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.45 }}
      onClick={onSelect}
      className="group text-left"
    >
      <Spotlight className="card card-hover h-full overflow-hidden p-5">
        <div className="flex items-center gap-3">
          <Avatar name={customer.name} size={44} />
          <div className="min-w-0">
            <div className="truncate font-semibold text-ink">{customer.name}</div>
            <div className="flex items-center gap-1 text-xs text-muted">
              <MapPin size={11} /> {customer.city}, {customer.state}
            </div>
          </div>
          <span
            className="ml-auto h-2.5 w-2.5 shrink-0 rounded-full"
            title={`${customer.persona} persona`}
            style={{ background: PERSONA_COLOR[customer.persona] ?? "var(--series-1)" }}
          />
        </div>
        <div className="mt-4 text-sm font-medium text-ink">{humanize(customer.intent)}</div>
        <p className="mt-1 line-clamp-2 text-xs italic text-ink2">“{customer.opening_message}”</p>
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <span
            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
            style={{ color: status.color, background: `color-mix(in srgb, ${status.color} 12%, transparent)` }}
          >
            {status.label}
          </span>
          {late && (
            <span className="rounded-full bg-[color-mix(in_srgb,var(--critical)_12%,transparent)] px-2 py-0.5 text-[11px] font-semibold text-bad">
              {customer.order.days_past_estimate} days late
            </span>
          )}
          <span className="chip py-0.5 text-[11px] capitalize">{customer.order.category || "order"}</span>
        </div>
        <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-brand opacity-70 transition-opacity group-hover:opacity-100">
          Continue as {customer.name.split(" ")[0]} <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
        </div>
      </Spotlight>
    </motion.button>
  );
}
