# Performance

Honest numbers from honest hardware. Everything on this page was measured on **one MacBook Pro**
(Apple M2 Pro, 10 cores, 16 GB RAM); the benchmark tools ship in
[the repository](https://github.com/hadielmougy/wiggle) so every figure is reproducible.

## The engine alone — one JVM

Embedded server, in-memory store, an 8-step fork/join workflow, 4 workers:

| execution mode | throughput |
|---|---|
| `SERVER` (a round-trip per step) | **2,481 instances/sec** · 19.8k durable step completions/sec |
| `LOCAL_SYNC` (chained, commit per step) | 3,313 instances/sec · 26.5k steps/sec |
| `LOCAL_ASYNC` (chained, batched commits) | **11,478 instances/sec · 91.8k steps/sec** |

`LOCAL_SYNC` / `LOCAL_ASYNC` are [worker-side step chaining](/docs/local-execution/): a worker
runs consecutive same-queue steps back-to-back, cutting server round-trips for step-heavy flows.

```bash
./gradlew :example:bench             # set WIGGLE_EXECUTION_MODE to reproduce
```

## A real deployment — Kubernetes, PostgreSQL cells

The kind-based lab cluster: 1 Raft coordinator, 2 cells (each its own server node **and its own
PostgreSQL 16**), reached over `kubectl port-forward`. We ramp the offered start rate and watch
**probe sojourn** — the end-to-end time of a fresh instance from `start()` to `COMPLETED`. Flat
sojourn means the cluster keeps up; monotonic growth means arrivals are outrunning it:

![Probe sojourn over time: at 300 starts/sec latency settles below one second; at 340 the backlog compounds, climbing to ~24s over 90 seconds.](/assets/img/bench-sojourn.svg)

| offered rate | window | end-to-end latency | verdict |
|---|---|---|---|
| **300/s** | 60s | settles **below 1s** | ✅ sustained |
| 340/s | 60s | plateau ≈4s, stable | ✅ holds a burst |
| 340/s | 90s | 4s → 24s, monotonic | ❌ queue piling |

**≈300 durable workflow starts/sec — ≈2,400 durable step executions/sec — sustained with
sub-second completion latency**; ~340/s survives a one-minute burst before backlog compounds.
Submit latency p50 ≈ 26 ms / p99 ≈ 130 ms throughout. Every step durably committed to PostgreSQL.

```bash
WIGGLE_COORDINATOR_URL=… WIGGLE_NAMESPACE=… BENCH_RATES="300,340" \
  ./gradlew :example:rateCeiling     # needs a running worker
```

## Adaptive polling — opt-in flags, measured

Each adaptivity reacts to what the last poll observed — never to queue depth — so an idle system
pays nothing extra:

| what | fixed cadence | adaptive | flag |
|---|---|---|---|
| timer/schedule promotion under backlog (2,000 due timers, default 1s tick × batch 100) | 19.9s — **100 timers/sec**, pinned to the batch÷tick floor | **1.18s — ~1,700/sec** (10,000 due drain in 1.61s ≈ 6,200/sec) | `WIGGLE_ADAPTIVE_HOUSEKEEPING` |
| cross-node dispatch latency (2-node cluster on one Postgres; submitter and the parked worker pinned to *different* nodes) | p50 **105ms** · p99 117ms | p50 **28ms** · p99 39ms | `WIGGLE_ADAPTIVE_FALLBACK_POLL` |

The fallback ramp costs no throughput: with it enabled the cluster still sustains the 300/s
ceiling (re-validated after fixing an early version that re-claimed fast on busy nodes and
measurably ate the ceiling). And a node-count A/B on this box confirmed the architecture claim:
2 nodes per cell did **not** raise the ceiling — nodes multiply availability and API capacity,
never database throughput.

![Adaptive polling before/after: timer drain 19.9s to 1.18s; cross-node dispatch p50 105ms to 28ms, p99 117ms to 39ms.](/assets/img/bench-adaptive.svg)

```bash
./gradlew :example:timerBench        # WIGGLE_ADAPTIVE_HOUSEKEEPING=true to compare
WIGGLE_SUBMIT_URL=… WIGGLE_WORKER_URL=… ./gradlew :example:fallbackProbe
```

## Resiliency under load — killing the coordinator

The control plane is a Raft group (embedded Ratis + RocksDB). To measure what its failure costs,
we drove a paced **150 starts/sec for 240 seconds** (36,001 starts) and **SIGKILL-ed the
coordinator JVM mid-run** — no graceful shutdown:

| metric | result |
|---|---|
| recovery (SIGKILL → ready, leadership re-acquired) | **9 seconds** |
| coordinator state after crash | **byte-exact** — policy revision, epoch ring, roster, definitions |
| start-availability gap | one contiguous **5.4s window** (810 of 36,001 starts failed, 2.25%) |
| running work during the outage | **unaffected** — probe sojourns held at ~260–290 ms throughout |
| integrity | all 35,191 accepted starts completed; drained to 0 running on both cells |

Workers keep serving cells they already know while the coordinator is down — only *new* start
routing needs it. The failover driver ships in the repo (`./gradlew :example:coordFailover`).

## Honest footnotes

- The submitter, worker, Kubernetes, coordinator, cells, and databases all shared those 10
  cores — the cluster figures are a **floor, not a ceiling**. Two cells on *one* box measure the
  same as one; cells buy throughput on separate hardware — that's the point of the model.
- Measured on **fresh databases** deliberately: after ~500k retained finished instances, the same
  setup showed ~2× the latency at 300/s. **Retention and purge cadence are capacity parameters**,
  not housekeeping afterthoughts.
- Cold JVMs lie. First runs after deploy include JIT warm-up; every figure above is from a warmed
  run with a discarded warm-up stage.
