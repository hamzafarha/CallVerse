# CallVerse architecture

Five layers, each a package of `src/callverse/` and a page of the control room. A lower layer
never imports a higher one; the rule is enforced by `import-linter` (`pyproject.toml`).

```mermaid
graph LR
    subgraph Data["Data layer"]
        RAW[Olist orders + Bitext messages] --> NB[notebooks 03-08<br/>run by data/pipeline.py]
        NB --> PQ[(Parquet tables)]
        PQ --> PA[Pandera contracts]
        PQ --> DB[(SQLite store)]
        KBD[KB documents] --> KB[(bge-m3 + FAISS)]
    end
    subgraph FS["Forecast & simulation"]
        PQ --> FC[LightGBM per intent<br/>rolling backtest]
        FC --> ER[Erlang C requirement]
        PQ --> SIM[SimPy engine<br/>skills, routers, costs]
    end
    subgraph Twin["Digital twin (LangGraph)"]
        CL[Client agent] --> WF[Workforce agent<br/>PPO routing + CP-SAT shifts]
        WF --> AD[Advisor agent<br/>RAG + SQLite tools]
        AD --> QA[Quality agent<br/>LLM judge]
    end
    subgraph Eval["Evaluation"]
        KPI[KPI engine] --> SC[Scorecard BO->DSO]
        CM[Component metrics] --> SC
    end
    subgraph Serve["Serving & MLOps"]
        API[FastAPI + WebSocket] --> UI[React control room]
        ML[MLflow] --- API
    end
    ER --> WF
    SIM --> WF
    DB --> AD
    KB --> AD
    SIM --> KPI
    QA --> KPI
    SC --> API
```

| Package | Layer | Depends on |
|---|---|---|
| `config`, `llm`, `tracking` | infrastructure | — |
| `data` | data | infrastructure |
| `forecasting`, `simulation` | forecast & simulation | data |
| `agents` (client, advisor, quality, workforce) | agents | simulation, forecasting, data |
| `twin` | digital twin | agents, simulation, forecasting |
| `orchestration` | LangGraph | agents, twin |
| `evaluation` | evaluation | everything above |
| `api` | serving | everything |

Runtime split: PPO trains on the fast SimPy + Gymnasium environment (sampled intents, no LLM
calls); the LLM agents validate behaviour on a smaller set of conversations. Model versions are
pinned (`callverse llm-pin`), seeds are fixed in `configs/`.

The full description (models, formulations, results) is in
[IP_VALIDATION_REPORT.md](IP_VALIDATION_REPORT.md).
