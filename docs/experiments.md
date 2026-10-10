# CallVerse Evaluation and Experiments Protocol

## Overview

This document details the benchmarking framework for evaluating forecasting models, workforce policies, advisor guidance, and counterfactual digital twin scenarios.

## Experiment Dimensions

### 1. Forecasting Benchmarks
- Compare baseline statistical models (moving average, seasonal naive) against regression and time-series approaches.
- Evaluate multi-horizon demand error (MAE, RMSE, WAPE).

### 2. Workforce Policy Benchmarks
- Compare static FIFO routing against skill-based heuristics and reinforcement learning policies.
- Evaluate average wait time, SLA attainment percentage, and advisor utilization variance.

### 3. Digital Twin Scenario Comparison
- Replay historical traces under counterfactual staffing schedules.
- Compare simulated queue metrics against historical baseline traces under stress scenarios (e.g. flash sales, system outages).

### 4. Advisor Quality Benchmarks
- Benchmark knowledge retrieval precision and recall.
- Evaluate automated transcript reviews using rubric scoring.
