# Experiment protocol

All experiments run with `callverse evaluate` and write their tables to `artifacts/evaluations/`
(and a summary run to MLflow, experiment `callverse-twin-scenarios`).

| Experiment | Question | Design | Output tables |
|---|---|---|---|
| Forecast backtest (`callverse forecast`) | does LightGBM beat "same day last week"? | 46 weekly origins, 7-day horizon, 5 models | `artifacts/forecasts/contact_forecast_backtest_*` |
| Twin fidelity | does the twin behave like the logs and like queueing theory? | Erlang C check (5 replications × 400 h); KS tests on 4 weeks | `twin_fidelity_*` |
| DSO3 scheduling | is CP-SAT cheaper than a fixed schedule at the service target? | 4 planners × 2 scenario weeks × 10 seeds, FIFO routing | `dso3_scheduling_*` |
| DSO1 routing | do learned routers beat FIFO? | (a) 20 unseen stressed days × 2 seeds; (b) 3 peak weeks × 10 seeds | `routing_comparison*`, `dso1_routing_*` |
| BO4 preparedness | does testing first help in peaks? | unprepared vs prepared CP-SAT plan, 3 peak scenarios × 10 seeds | `bo4_preparedness_*` |
| DSO2 conversations | how good are the advisor variants? | template / rag / rag_policy batches on sampled contacts | `dso2_agents_*` |
| DSO2 retrieval | does bge-m3 beat keyword search? | 255 Bitext questions (15 per intent) | `dso2_rag_retrieval.csv` |
| DSO2 faithfulness | are answers supported by the evidence? | sentence-level cosine to tool results + cited policy | `dso2_rag_faithfulness.csv` |
| DSO2 judge | can the judge be trusted? | judge vs labels (human if ≥ 20, else proxy), kappa + Spearman | `dso2_judge_calibration_*` |

Statistics: every option is simulated on the same random customers (common random numbers);
differences are paired by seed and reported with a 95% Student-t interval; a difference is
called significant only when the interval excludes zero. The scorecard
(`scorecard.json`) applies the switch rules of the DSO document.
