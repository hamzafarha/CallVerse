/**
 * The "MCP server" card of the Agent theater: what the CallVerse MCP server publishes and how to connect.
 *
 * MCP (Model Context Protocol) is a standard plug between AI apps and tools. The server publishes a menu:
 * tools (to call), resources (to read) and prompts (to start from). The Advisor agent reads this menu and
 * calls its tools through it; Claude Desktop or the MCP Inspector can connect to the same server. The data
 * comes from GET /api/mcp, which reads the menu through the protocol itself (src/callverse/mcp/).
 */
import { Card, Loading, Pill, clsx, useApi } from "@callverse/shared";
import { Bot, Copy, FileText, Laptop, MessageSquareText, Plug, Wrench } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

const GROUPS: { id: string; label: string }[] = [
  { id: "advisor", label: "Advisor tools (the agent uses these)" },
  { id: "case", label: "Case (outside apps)" },
  { id: "twin", label: "Digital twin (outside apps)" },
];

/** Copy a text to the clipboard, with a small confirmation. */
function copy(text: string, what: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success(`${what} copied`))
    .catch(() => toast.error("Copy failed: select the text instead"));
}

export function McpServer() {
  const mcp = useApi<any>("/api/mcp");
  const [tab, setTab] = useState<"tools" | "resources" | "prompts">("tools");
  const data = mcp.data;
  const viaMcp = data?.advisor?.tool_transport === "mcp";

  return (
    <Card
      icon={<Plug size={18} />}
      title="MCP server"
      subtitle="Model Context Protocol: one standard plug between AI apps and CallVerse. The Advisor agent discovers its tools here (tools/list) and calls them through it (tools/call); Claude Desktop or the MCP Inspector can use the same server."
      action={
        data && (
          <Pill color={viaMcp ? "var(--good-text)" : "var(--warning)"}>
            <Bot size={12} /> Advisor tools: {viaMcp ? "via MCP" : "direct"}
          </Pill>
        )
      }
    >
      {mcp.loading && !data && <Loading text="Connecting to the MCP server" />}
      {mcp.error && <div className="text-sm text-bad">{mcp.error}</div>}
      {data && (
        <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
          {/* The menu: tools / resources / prompts. */}
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              {(
                [
                  ["tools", `${data.tools.length} tools`, Wrench],
                  ["resources", `${data.resources.length} resources`, FileText],
                  ["prompts", `${data.prompts.length} prompts`, MessageSquareText],
                ] as const
              ).map(([id, label, Icon]) => (
                <button key={id} className={clsx("btn px-3 py-1.5 text-xs", tab === id ? "btn-primary" : "btn-ghost")} onClick={() => setTab(id)}>
                  <Icon size={13} /> {label}
                </button>
              ))}
              <span className="ml-auto font-mono text-[11px] text-muted">protocol {data.protocol}</span>
            </div>
            <div className="max-h-[420px] space-y-4 overflow-y-auto pr-1">
              {tab === "tools" &&
                GROUPS.map((group) => {
                  const tools = data.tools.filter((t: any) => t.group === group.id);
                  if (!tools.length) return null;
                  return (
                    <div key={group.id}>
                      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">{group.label}</div>
                      <div className="space-y-1.5">
                        {tools.map((t: any) => (
                          <div key={t.name} className="rounded-lg border border-line px-3 py-2">
                            <div className="flex items-baseline gap-2">
                              <span className="font-mono text-xs font-semibold text-ink">{t.name}</span>
                              <span className="truncate font-mono text-[10px] text-muted">
                                ({t.arguments.map((a: string) => (t.required.includes(a) ? a : `${a}?`)).join(", ")})
                              </span>
                            </div>
                            <p className="mt-0.5 text-[11px] leading-snug text-ink2">{t.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              {tab === "resources" && (
                <div className="space-y-1.5">
                  {data.resources.map((r: any) => (
                    <div key={r.uri} className="rounded-lg border border-line px-3 py-2">
                      <div className="text-xs font-semibold text-ink">{r.title}</div>
                      <div className="font-mono text-[10px] text-muted">{r.uri}</div>
                    </div>
                  ))}
                  {data.templates.map((t: any) => (
                    <div key={t.uri_template} className="rounded-lg border border-dashed border-line px-3 py-2 text-[11px] text-ink2">
                      Address pattern: <span className="font-mono">{t.uri_template}</span>
                    </div>
                  ))}
                </div>
              )}
              {tab === "prompts" && (
                <div className="space-y-1.5">
                  {data.prompts.map((p: any) => (
                    <div key={p.name} className="rounded-lg border border-line px-3 py-2">
                      <div className="flex items-baseline gap-2">
                        <span className="text-xs font-semibold text-ink">{p.title}</span>
                        <span className="font-mono text-[10px] text-muted">
                          {p.name}({p.arguments.join(", ")})
                        </span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-ink2">{p.description}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* The three ways in (transports). */}
          <div className="space-y-3 text-[11px] leading-relaxed text-ink2">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Three ways to connect</div>
            <div className="rounded-xl bg-raised p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-ink">
                <Bot size={13} className="text-brand" /> 1. In the same program: the Advisor agent
              </div>
              Each turn, the agent connects, lists the tools and sends the LLM's choices as tools/call. Gating stays the agent's decision: the LLM only sees the tools allowed at this stage.
            </div>
            <div className="rounded-xl bg-raised p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-ink">
                <Laptop size={13} className="text-brand" /> 2. stdio: Claude Desktop
              </div>
              Settings › Developer › Edit Config, paste this, restart Claude Desktop:
              <pre className="mt-1.5 max-h-40 overflow-auto rounded-lg bg-surface p-2 font-mono text-[10px] text-ink">{JSON.stringify(data.connect.claude_desktop_config, null, 2)}</pre>
              <button className="btn btn-ghost mt-1.5 px-2 py-1 text-[11px]" onClick={() => copy(JSON.stringify(data.connect.claude_desktop_config, null, 2), "Claude Desktop config")}>
                <Copy size={12} /> Copy config
              </button>
            </div>
            <div className="rounded-xl bg-raised p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-ink">
                <Plug size={13} className="text-brand" /> 3. HTTP: the MCP Inspector
              </div>
              While <span className="font-mono">callverse serve</span> runs, MCP clients on this PC connect to{" "}
              <span className="break-all font-mono font-semibold text-ink">{data.connect.http_url}</span> (Streamable HTTP). Or start the Inspector on the stdio server:
              <pre className="mt-1.5 overflow-x-auto rounded-lg bg-surface p-2 font-mono text-[10px] text-ink">{data.connect.inspector}</pre>
              <button className="btn btn-ghost mt-1.5 px-2 py-1 text-[11px]" onClick={() => copy(data.connect.inspector, "Inspector command")}>
                <Copy size={12} /> Copy command
              </button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
