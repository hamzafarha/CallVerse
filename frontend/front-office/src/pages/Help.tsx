import { Markdown, Skeleton, motion, slug, useApi } from "@callverse/shared";
import { ArrowLeft, Lock, MessageCircle } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { HelpSearch } from "../components/HelpSearch";

export default function HelpPage() {
  const { articleId } = useParams();
  return articleId ? <Article id={articleId} /> : <Index />;
}

function Index() {
  const articles = useApi<any[]>("/api/kb/articles");
  return (
    <div className="space-y-10">
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="font-display text-4xl font-semibold text-ink md:text-5xl">Help centre</h1>
        <p className="mt-3 text-ink2">
          The same articles our AI advisor reads before answering you. Search them in your own words.
        </p>
        <div className="mt-6 text-left">
          <HelpSearch large />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {articles.data
          ? articles.data.map((article, i) => (
              <motion.div key={article.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                <Link to={`/help/${article.id}`} className="card card-hover group block h-full p-6">
                  <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted">
                    {article.type}
                    {article.internal && (
                      <span className="inline-flex items-center gap-1 normal-case tracking-normal">
                        <Lock size={11} /> staff
                      </span>
                    )}
                  </div>
                  <div className="mt-2 text-lg font-semibold text-ink group-hover:text-brand">{article.title}</div>
                  <p className="mt-2 line-clamp-3 text-sm text-ink2">{article.summary}</p>
                  <div className="mt-4 flex flex-wrap gap-1.5">
                    {article.sections.slice(0, 3).map((s: string) => (
                      <span key={s} className="chip py-0.5 text-[11px]">
                        {s}
                      </span>
                    ))}
                    {article.sections.length > 3 && <span className="chip py-0.5 text-[11px]">+{article.sections.length - 3}</span>}
                  </div>
                </Link>
              </motion.div>
            ))
          : Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-48" />)}
      </div>
    </div>
  );
}

function Article({ id }: { id: string }) {
  const { data, error } = useApi<any>(`/api/kb/articles/${id}`);
  const location = useLocation();
  const anchor = location.hash.slice(1);
  useEffect(() => {
    if (data && anchor) window.setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }), 300);
    else window.scrollTo({ top: 0 });
  }, [data, anchor]);
  if (error) return <p className="text-bad">{error}</p>;
  return (
    <div className="grid gap-10 lg:grid-cols-[220px_1fr_260px]">
      <aside className="hidden lg:block">
        <div className="sticky top-24 space-y-1">
          <Link to="/help" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
            <ArrowLeft size={14} /> Help centre
          </Link>
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">On this page</div>
          {(data?.sections ?? []).map((s: string) => (
            <a
              key={s}
              href={`#${slug(s)}`}
              className={`block rounded-lg px-2 py-1.5 text-sm transition-colors hover:bg-raised ${anchor === slug(s) ? "bg-raised font-medium text-brand" : "text-ink2"}`}
            >
              {s}
            </a>
          ))}
        </div>
      </aside>
      <article className="card min-w-0 p-6 md:p-10">
        {data ? <Markdown text={data.markdown} highlight={anchor} /> : <Skeleton className="h-96" />}
      </article>
      <aside>
        <div className="card sticky top-24 overflow-hidden p-6">
          <div className="pointer-events-none absolute -right-10 -top-10 h-32 w-32 rounded-full opacity-30 blur-2xl gradient-brand" />
          <MessageCircle className="text-brand" />
          <div className="mt-3 font-semibold text-ink">Still need help?</div>
          <p className="mt-1 text-sm text-ink2">Our AI advisor reads this article for you and checks your order.</p>
          <Link to="/chat" className="btn btn-primary mt-4 w-full">
            Start a chat
          </Link>
        </div>
      </aside>
    </div>
  );
}
