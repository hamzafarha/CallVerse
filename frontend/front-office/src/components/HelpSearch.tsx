import { AnimatePresence, getJson, motion, slug } from "@callverse/shared";
import { ArrowRight, Loader2, Search, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

interface Hit {
  chunk_id: string;
  article: string;
  section: string;
  text: string;
  score: number;
}

const EXAMPLES = ["my parcel is late", "how do I get a refund?", "item arrived broken", "change delivery address"];

/** Semantic search over the knowledge base (bge-m3 + FAISS), as you type. */
export function HelpSearch({ large = false }: { large?: boolean }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [meta, setMeta] = useState<{ retriever: string; latency_ms: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);
  const [cursor, setCursor] = useState(0);
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.trim().length < 3) {
      setHits([]);
      return;
    }
    setLoading(true);
    const timer = window.setTimeout(() => {
      getJson(`/api/kb/search?k=5&q=${encodeURIComponent(query)}`)
        .then((r) => {
          setHits(r.results);
          setMeta({ retriever: r.retriever, latency_ms: r.latency_ms });
          setCursor(0);
        })
        .catch(() => setHits([]))
        .finally(() => setLoading(false));
    }, 280);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setFocused(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);

  const open = (hit: Hit) => navigate(`/help/${hit.article}#${slug(hit.section)}`);
  const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
  const mark = (text: string) =>
    text.split(/(\s+)/).map((w, i) =>
      words.some((q) => w.toLowerCase().includes(q)) ? (
        <mark key={i} className="rounded bg-[var(--brand-soft)] px-0.5 text-ink">
          {w}
        </mark>
      ) : (
        w
      ),
    );

  return (
    <div ref={box} className="relative w-full">
      <div className={`ring-gradient rounded-2xl ${focused ? "shadow-glow" : "shadow-soft"} transition-shadow`}>
        <div className="flex items-center gap-3 rounded-2xl bg-surface px-4">
          {loading ? <Loader2 size={20} className="animate-spin text-brand" /> : <Search size={20} className="text-brand" />}
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setCursor((c) => Math.min(hits.length - 1, c + 1));
              if (e.key === "ArrowUp") setCursor((c) => Math.max(0, c - 1));
              if (e.key === "Enter" && hits[cursor]) open(hits[cursor]);
            }}
            placeholder="Describe your problem in your own words…"
            className={`w-full bg-transparent text-ink outline-none placeholder:text-muted ${large ? "h-16 text-lg" : "h-12 text-[15px]"}`}
          />
          <span className="hidden items-center gap-1 rounded-lg bg-[var(--brand-soft)] px-2 py-1 text-[11px] font-medium text-brand sm:inline-flex">
            <Sparkles size={12} /> semantic
          </span>
        </div>
      </div>
      {!query && large && (
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button key={example} onClick={() => { setQuery(example); setFocused(true); }} className="chip transition-colors hover:border-brand hover:text-brand">
              {example}
            </button>
          ))}
        </div>
      )}
      <AnimatePresence>
        {focused && hits.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6 }}
            className="card absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden p-2 shadow-lift"
          >
            {hits.map((hit, i) => (
              <button
                key={hit.chunk_id}
                onMouseEnter={() => setCursor(i)}
                onClick={() => open(hit)}
                className={`flex w-full items-start gap-3 rounded-xl p-3 text-left transition-colors ${cursor === i ? "bg-raised" : ""}`}
              >
                <div className="mt-0.5 w-10 shrink-0">
                  <div className="h-1.5 rounded-full bg-sunken">
                    <div className="h-1.5 rounded-full gradient-brand" style={{ width: `${Math.max(8, Math.min(100, hit.score * 100))}%` }} />
                  </div>
                  <div className="mt-1 text-center text-[10px] tabular text-muted">{hit.score.toFixed(2)}</div>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-ink">{hit.section}</div>
                  <div className="text-[11px] uppercase tracking-wide text-muted">{hit.article.replace(/_/g, " ")}</div>
                  <p className="mt-1 line-clamp-2 text-xs text-ink2">{mark(hit.text.replace(/\s+/g, " "))}</p>
                </div>
                <ArrowRight size={15} className="mt-1 text-muted" />
              </button>
            ))}
            {meta && (
              <div className="border-t border-line px-3 pb-1 pt-2 text-[11px] text-muted">
                {meta.retriever} · {meta.latency_ms.toFixed(0)} ms · cosine similarity
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
