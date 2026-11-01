import { GROUP_COLOR, Reveal, Skeleton, Spotlight, Stagger, StaggerItem, motion, useApi } from "@callverse/shared";
import {
  ArrowRight,
  BadgeCheck,
  BookOpen,
  FileText,
  MessageCircle,
  Package,
  PackageX,
  RotateCcw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { CustomerCard } from "../components/CustomerCard";
import { HelpSearch } from "../components/HelpSearch";
import { HeroChatDemo } from "../components/HeroChatDemo";
import { useCustomer } from "../customer";

const TOPICS = [
  { group: "wismo", icon: Package, title: "Where is my order?", text: "Tracking, delivery dates, late or lost parcels.", article: "order_status_and_tracking" },
  { group: "cancel_refund", icon: RotateCcw, title: "Cancel or refund", text: "Cancel before shipping, refund timings, refund status.", article: "refund_policy" },
  { group: "post_delivery", icon: PackageX, title: "Problem with an item", text: "Damaged, wrong or missing items, returns and exchanges.", article: "damaged_wrong_missing_items" },
  { group: "order_admin", icon: FileText, title: "Invoices & changes", text: "Invoices, address changes, payment questions.", article: "invoices" },
];

const STEPS = [
  { icon: Sparkles, title: "Understand", text: "An intent classifier reads your message and the Workforce agent routes you to the right desk." },
  { icon: ScanSearch, title: "Retrieve", text: "bge-m3 embeddings find the exact policy sections that apply (FAISS, cosine similarity)." },
  { icon: Workflow, title: "Verify & decide", text: "Your order is checked in our database; a rules engine applies the policy. The AI never invents a promise." },
  { icon: ShieldCheck, title: "Answer & review", text: "SmolLM3 writes the reply in plain words; an independent Granite judge grades every chat." },
];

export default function HomePage() {
  const customers = useApi<any[]>("/api/portal/customers");
  const articles = useApi<any[]>("/api/kb/articles");
  const { setCustomer } = useCustomer();
  const navigate = useNavigate();

  return (
    <div className="space-y-24">
      {/* ------------------------------------------------------------ hero */}
      <section className="grid items-center gap-14 pt-4 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="chip mb-6 border-[color-mix(in_srgb,var(--brand)_30%,transparent)] text-brand">
            <BadgeCheck size={14} /> Answers grounded in our policies · checked against your order
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="font-display text-5xl font-semibold leading-[1.05] tracking-tight text-ink md:text-6xl"
          >
            Help that already <span className="gradient-text">knows your order.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }} className="mt-5 max-w-xl text-lg leading-relaxed text-ink2">
            Search our help centre in your own words, or chat with our AI advisor. It checks your order, applies the
            store's rules and hands you to a specialist when a human is needed.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="mt-8 max-w-xl">
            <HelpSearch large />
          </motion.div>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} className="mt-8 flex flex-wrap gap-3">
            <Link to="/chat" className="btn btn-primary px-5 py-3 text-[15px]">
              <MessageCircle size={17} /> Chat with an advisor
            </Link>
            <a href="#customers" className="btn btn-ghost px-5 py-3 text-[15px]">
              <Package size={17} /> Track an order
            </a>
          </motion.div>
        </div>
        <HeroChatDemo />
      </section>

      {/* ---------------------------------------------------------- topics */}
      <section>
        <Reveal>
          <h2 className="text-3xl font-semibold text-ink">What do you need help with?</h2>
          <p className="mt-2 text-ink2">The four problem families our advisors handle, from the real customer contacts.</p>
        </Reveal>
        <Stagger className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TOPICS.map((topic) => (
            <StaggerItem key={topic.group}>
              <Link to={`/help/${topic.article}`} className="group block h-full">
                <Spotlight className="card card-hover h-full p-6">
                  <div
                    className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-soft transition-transform group-hover:scale-110 group-hover:-rotate-6"
                    style={{ background: GROUP_COLOR[topic.group] }}
                  >
                    <topic.icon size={22} />
                  </div>
                  <div className="text-lg font-semibold text-ink">{topic.title}</div>
                  <p className="mt-1.5 text-sm leading-relaxed text-ink2">{topic.text}</p>
                  <div className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand">
                    Read the guide <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" />
                  </div>
                </Spotlight>
              </Link>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      {/* ------------------------------------------------------- customers */}
      <section id="customers" className="scroll-mt-24">
        <Reveal>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="chip mb-3 text-brand">Demo</div>
              <h2 className="text-3xl font-semibold text-ink">Try it as a real customer</h2>
              <p className="mt-2 max-w-2xl text-ink2">
                Each card is a real (anonymised) Olist order and the message its customer sent. Pick one: you will see the
                order as it was that day, then chat with the AI advisor about it.
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted">
              {["impatient", "normal", "patient"].map((p, i) => (
                <span key={p} className="inline-flex items-center gap-1.5 capitalize">
                  <span className="h-2 w-2 rounded-full" style={{ background: ["var(--critical)", "var(--series-1)", "var(--series-3)"][i] }} /> {p}
                </span>
              ))}
            </div>
          </div>
        </Reveal>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {customers.data
            ? customers.data.map((c, i) => (
                <CustomerCard
                  key={c.contact_id}
                  index={i}
                  customer={c}
                  onSelect={() => {
                    setCustomer({ contact_id: c.contact_id, name: c.name });
                    navigate(`/account/${c.contact_id}`);
                  }}
                />
              ))
            : Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-56" />)}
        </div>
        {customers.error && <p className="mt-4 text-sm text-bad">Could not load the demo customers: {customers.error}</p>}
      </section>

      {/* ------------------------------------------------------ how it works */}
      <section className="card overflow-hidden p-8 md:p-12">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full opacity-30 blur-3xl" style={{ background: "var(--brand)" }} />
        <Reveal>
          <h2 className="text-3xl font-semibold text-ink">How our AI advisor answers you</h2>
          <p className="mt-2 max-w-2xl text-ink2">Four steps, all running on our own servers. No data leaves the company.</p>
        </Reveal>
        <div className="relative mt-10 grid gap-8 md:grid-cols-4">
          <motion.div
            className="absolute left-0 right-0 top-6 hidden h-0.5 origin-left gradient-brand md:block"
            initial={{ scaleX: 0 }}
            whileInView={{ scaleX: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
          />
          {STEPS.map((step, i) => (
            <Reveal key={step.title} delay={0.15 * i}>
              <div className="relative">
                <div className="relative z-10 mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-line bg-surface text-brand shadow-soft">
                  <step.icon size={20} />
                </div>
                <div className="text-xs font-semibold text-muted">Step {i + 1}</div>
                <div className="mt-1 text-lg font-semibold text-ink">{step.title}</div>
                <p className="mt-1.5 text-sm leading-relaxed text-ink2">{step.text}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------- articles */}
      <section>
        <Reveal>
          <div className="flex items-end justify-between">
            <h2 className="text-3xl font-semibold text-ink">Popular guides</h2>
            <Link to="/help" className="btn btn-ghost">
              <BookOpen size={15} /> All articles
            </Link>
          </div>
        </Reveal>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {(articles.data ?? [])
            .filter((a) => !a.internal)
            .slice(0, 6)
            .map((article, i) => (
              <motion.div key={article.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                <Link to={`/help/${article.id}`} className="card card-hover group block h-full p-5">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{article.type}</div>
                  <div className="mt-1 font-semibold text-ink group-hover:text-brand">{article.title}</div>
                  <p className="mt-2 line-clamp-2 text-sm text-ink2">{article.summary}</p>
                  <div className="mt-3 text-xs text-muted">{article.sections.length} sections</div>
                </Link>
              </motion.div>
            ))}
        </div>
      </section>
    </div>
  );
}
