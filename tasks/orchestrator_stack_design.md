# Klaw — High-Performance Data Orchestrator Stack

This document captures the agreed architecture, layers, and library/tooling decisions for **Klaw**, a **Python-first orchestrator with Rust backends**, optimized for performance, modularity, and future evolution.

______________________________________________________________________

## 🎯 Goals

- Python ergonomics for orchestration logic.
- Rust performance for compute and infrastructure services.
- Clear separation between control plane and data plane.
- Binary, typed internal protocols (avoid JSON/REST internally).
- Scalable execution and observability.
- Human-friendly interfaces layered on top.

______________________________________________________________________

## 🧱 Layered Architecture Overview

```
Clients (Web / TUI / CLI)
        │
        ▼
   🌐 Axum API (Auth + Facade)
        │
        ▼
 🚀 Arrow Flight (Control & Data RPC)
        │
        ▼
 🐍 Python Orchestrator ──▶ ⚡ Ray Scheduler ──▶ 🦀 Rust Engines
        │                                          │
        └─────────────── 🐘 Timescale/Postgres ◀───┘
                               │
                               ▼
                       📊 DuckLake / Parquet

   🕰️ Rust Tokio Cron Scheduler ──▶ Arrow Flight (Triggers)
```

Each layer has a single responsibility and communicates through well-defined interfaces.

______________________________________________________________________

## 🧠 Control Plane — Python Orchestrator

**Responsibility**

- Define workflows, assets, and stages.
- Build and validate dependency graphs.
- Decide readiness and execution order.
- Track run/stage state and emit events.
- Expose internal control via Arrow Flight.

**Key Characteristics**

- Never handles large datasets.
- Operates on typed commands and metadata.
- Brain of the system.

**Language**: Python

______________________________________________________________________

## ⚡ Execution Plane — Ray

**Responsibility**

- Distributed task scheduling.
- Resource-aware placement (CPU/GPU/mem).
- Parallel execution and basic retries.

**Key Characteristics**

- Executes stage tasks once submitted.
- Does not reason about DAG semantics.
- Moves only small metadata.

**Language**: Python (Ray runtime)

______________________________________________________________________

## 🧬 Data Plane — Arrow Flight

**Responsibility**

- High-performance binary RPC.
- Stream Arrow record batches.
- Internal control actions (DoAction).

**Key Characteristics**

- gRPC-based.
- Async, zero-copy friendly.
- Single protocol for control + data.

**Languages**: Python & Rust

______________________________________________________________________

## 🦀 Compute Plane — Rust Engines

**Responsibility**

- Heavy data processing.
- Execute Polars, DuckDB, and custom Rust logic.
- Read/write Parquet & DuckLake.
- Stream Arrow in/out.

**Key Characteristics**

- Stateless async services.
- Horizontally scalable.
- Optimized for throughput.

**Language**: Rust (Tokio async)

______________________________________________________________________

## 🗃️ Storage Plane — DuckLake

**Responsibility**

- Store datasets as Parquet.
- Manage snapshots/manifests.
- Enable time travel & versioning.

**Key Characteristics**

- Source of truth for data assets.
- Shared by engines and analytics.

**Tech**: DuckLake + Parquet + Object Storage

______________________________________________________________________

## 🐘 Metadata & Observability Plane — Timescale/Postgres

**Responsibility**

- Runs and stage transitions.
- Events and metrics.
- Durations, counts, outcomes.

**Key Characteristics**

- Append-heavy time-series data.
- Queryable operational history.

**Tech**: Postgres + TimescaleDB

______________________________________________________________________

## 🕰️ Trigger Plane — Rust Tokio Cron Scheduler

**Responsibility**

- Time-based triggers (cron).
- Wake up the orchestrator.

**Key Characteristics**

- No orchestration logic.
- Emits control actions via Arrow Flight.

**Language**: Rust (Tokio)

______________________________________________________________________

## 🌐 Interface Plane — Axum Facade

**Responsibility**

- Human-facing HTTP/JSON API.
- Auth, RBAC, rate limiting.
- Translate HTTP → Flight actions.

**Key Characteristics**

- Thin gateway.
- No business logic.

**Language**: Rust

______________________________________________________________________

## 🖥️ Clients

**Web UI**

- Explore DAGs, runs, assets, logs.
- Real-time dashboards.

**TUI**

- Ops-friendly terminal interface.

**CLI**

- Automation and scripting.

All clients talk to the Axum API.

______________________________________________________________________

## 🧭 Telemetry & Observability

**Principle** Emit once, export many.

**What we track**

- Structured logs.
- Metrics (durations, counts, throughput).
- Logical traces via run_id/stage_id.

**Strategy**

- Core: structlog (Python) + tracing (Rust).
- Persist business metrics/events in Timescale.
- Layer exporters/connectors to:
  - OpenTelemetry,
  - Grafana (Loki/Tempo/Mimir),
  - Datadog,
  - Sentry,
  - or other backends.

Exporters are configured, not hard-coded.

______________________________________________________________________

## 📚 Library & Tooling Decisions

| Layer              | Role                      | Language  | Libraries / Tools                                                     |
| ------------------ | ------------------------- | --------- | --------------------------------------------------------------------- |
| 🧠 Control Plane   | Orchestration, DAG, state | Python    | `rustworkx`, `msgspec`, `structlog`, `pydantic`, `fastapi` (internal) |
| ⚡ Execution Plane | Task scheduling           | Python    | `ray`                                                                 |
| 🧬 Data Plane      | RPC + Arrow streaming     | Py + Rust | `pyarrow.flight`, `arrow-flight`, `tonic`                             |
| 🦀 Compute Plane   | Heavy compute             | Rust      | `tokio`, `polars`, `duckdb`, `arrow`, `arrow-flight`, `tracing`       |
| 🗃️ Storage Plane   | Versioned lake            | —         | DuckLake, Parquet, S3/GCS/FS                                          |
| 🐘 Metadata / Ops  | Runs & metrics            | SQL       | Postgres, TimescaleDB                                                 |
| 🕰️ Trigger Plane   | Cron scheduling           | Rust      | `tokio_cron_scheduler` (or `cron`), `tokio`                           |
| 🌐 Interface Plane | HTTP facade               | Rust      | `axum`, `tower`, `reqwest`                                            |
| 🔐 Auth            | Identity                  | SaaS      | Clerk                                                                 |
| 🖥️ Web UI          | Browser UI                | TS        | Svelte                                                                |
| 🧵 TUI             | Terminal UI               | Rust      | ratatui                                                               |
| 💻 CLI             | CLI tooling               | Rust      | clap, reqwest                                                         |
| 🪵 Logging (Py)    | Structured logs           | Python    | structlog                                                             |
| 🪵 Logging (Rs)    | Structured logs           | Rust      | tracing, tracing-subscriber                                           |
| 📦 Serialization   | Typed commands            | Py + Rust | msgspec (MessagePack), rmp-serde                                      |
| 📊 Telemetry       | Exporters                 | Py + Rust | OpenTelemetry SDKs, Datadog, Sentry                                   |

______________________________________________________________________

## 🧠 Key Design Principles

- **Separation of concerns**: brain, nerves, muscles, memory.
- **Binary-first internals**: Arrow + MessagePack.
- **Typed commands everywhere**.
- **Replaceable layers**: Ray ↔ Temporal, DuckLake ↔ Lance, etc.
- **Fast core, friendly edges**.

______________________________________________________________________

## 🏁 Summary

This stack defines a modern data orchestration platform:

- 🧠 Python brain for semantics.
- ⚡ Ray for distributed execution.
- 🚀 Arrow Flight as the nervous system.
- 🦀 Rust engines for raw performance.
- 📊 DuckLake for data truth.
- 🐘 Timescale for operational memory.
- 🕰️ Rust cron as the alarm clock.
- 🌐 Axum + Clerk as the human gateway.

Built to scale, evolve, and stay understandable.
