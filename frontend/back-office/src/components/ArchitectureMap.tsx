import { motion } from "@callverse/shared";
import { Activity, Database, FlaskConical, Server, TrendingUp, type LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface Layer {
  id: string;
  title: string;
  lines: string[];
  color: string;
  icon: LucideIcon;
  to: string;
}

const LAYERS: Layer[] = [
  { id: "data", title: "Data layer", lines: ["Olist orders · Bitext intents", "contacts · tickets · chats", "SQLite · bge-m3 KB"], color: "var(--layer-data)", icon: Database, to: "/data" },
  { id: "forecast", title: "Forecast", lines: ["LightGBM per intent", "vs naive · SARIMA · Prophet", "rolling backtest"], color: "var(--layer-sim)", icon: TrendingUp, to: "/forecast" },
  { id: "twin", title: "Digital twin", lines: ["SimPy contact centre", "4 agents · LangGraph", "PPO · CP-SAT · RAG · judge"], color: "var(--layer-agents)", icon: Activity, to: "/twin" },
  { id: "eval", title: "Evaluation", lines: ["scenarios × seeds", "95% CIs · KPI engine", "BO → DSO scorecard"], color: "var(--layer-eval)", icon: FlaskConical, to: "/evaluation" },
  { id: "serve", title: "Serving & MLOps", lines: ["FastAPI · WebSocket", "React front + back office", "MLflow · Docker · CI"], color: "var(--layer-serve)", icon: Server, to: "/mlops" },
];
const AGENTS = ["Client", "Advisor", "Quality", "Workforce"];

const W = 1000;
const H = 250;
const BOX_W = 168;
const BOX_H = 150;
const GAP = (W - LAYERS.length * BOX_W) / (LAYERS.length - 1);
const x = (i: number) => i * (BOX_W + GAP);

/** The five layers of the architecture with data flowing between them. */
export function ArchitectureMap() {
  const navigate = useNavigate();
  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[760px]" role="img" aria-label="CallVerse architecture">
        <defs>
          <linearGradient id="flow-gradient" x1="0" x2="1">
            <stop offset="0%" stopColor="var(--brand)" />
            <stop offset="100%" stopColor="var(--brand-2)" />
          </linearGradient>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {LAYERS.slice(0, -1).map((_, i) => {
          const x1 = x(i) + BOX_W;
          const x2 = x(i + 1);
          const y = 40 + BOX_H / 2;
          const path = `M ${x1} ${y} L ${x2} ${y}`;
          return (
            <g key={i}>
              <path d={path} stroke="url(#flow-gradient)" strokeWidth={2} strokeDasharray="5 6" fill="none" style={{ animation: "flow 1.2s linear infinite" }} />
              {[0, 0.5].map((offset) => (
                <circle key={offset} r={3.5} fill="var(--brand-2)" filter="url(#glow)" visibility="hidden">
                  <set attributeName="visibility" to="visible" begin={`${offset * 1.8 + i * 0.3}s`} />
                  <animateMotion dur="1.8s" begin={`${offset * 1.8 + i * 0.3}s`} repeatCount="indefinite" path={path} />
                </circle>
              ))}
            </g>
          );
        })}
        {/* feedback loop: evaluation results drive the next plan */}
        <path
          d={`M ${x(3) + BOX_W / 2} ${40 + BOX_H} C ${x(3) + BOX_W / 2} ${H - 2}, ${x(2) + BOX_W / 2} ${H - 2}, ${x(2) + BOX_W / 2} ${40 + BOX_H}`}
          stroke="var(--baseline)"
          strokeWidth={1.5}
          strokeDasharray="3 5"
          fill="none"
          style={{ animation: "flow 2s linear infinite reverse" }}
        />
        <text x={(x(2) + x(3)) / 2 + BOX_W / 2} y={H - 6} textAnchor="middle" fontSize={10} fill="var(--text-muted)">
          test first, then decide
        </text>
        {LAYERS.map((layer, i) => (
          <motion.g
            key={layer.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.12, duration: 0.5 }}
            style={{ cursor: "pointer" }}
            onClick={() => navigate(layer.to)}
          >
            <rect x={x(i)} y={40} width={BOX_W} height={BOX_H} rx={18} fill="var(--surface-1)" stroke="var(--hairline)" />
            <rect x={x(i) + 22} y={40} width={BOX_W - 44} height={3} rx={1.5} fill={layer.color} />
            <circle cx={x(i) + 26} cy={74} r={15} fill={layer.color} opacity={0.15} />
            <foreignObject x={x(i) + 16} y={64} width={20} height={20}>
              <layer.icon size={20} color={layer.color} />
            </foreignObject>
            <text x={x(i) + 50} y={80} fontSize={14} fontWeight={600} fill="var(--text-primary)" fontFamily="Space Grotesk Variable, sans-serif">
              {layer.title}
            </text>
            {layer.id === "twin" ? (
              AGENTS.map((agent, j) => (
                <g key={agent}>
                  <rect x={x(i) + 14 + (j % 2) * 72} y={98 + Math.floor(j / 2) * 30} width={66} height={24} rx={8} fill="var(--brand-soft)" />
                  <text x={x(i) + 47 + (j % 2) * 72} y={114 + Math.floor(j / 2) * 30} fontSize={10.5} fontWeight={600} textAnchor="middle" fill="var(--brand)">
                    {agent}
                  </text>
                </g>
              ))
            ) : (
              layer.lines.map((line, j) => (
                <text key={line} x={x(i) + 16} y={110 + j * 20} fontSize={11} fill="var(--text-secondary)">
                  {line}
                </text>
              ))
            )}
            {layer.id === "twin" && (
              <text x={x(i) + 16} y={172} fontSize={10} fill="var(--text-muted)">
                LangGraph orchestration
              </text>
            )}
          </motion.g>
        ))}
      </svg>
    </div>
  );
}
