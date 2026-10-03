# Performance

Everything on this page was measured on GCP against Cloud SQL for PostgreSQL. The provisioning
script and the benchmark ship in [the repository](https://github.com/hadielmougy/wiggle), so you
can reproduce every figure.

## The ceiling of one node

**7,200 durable step executions/sec (900 workflow instances/sec)**, sustained by one server node.
Every step is committed to PostgreSQL, and each instance completes in about 3 seconds end to end.
At lighter load the end-to-end time is about 260ms: 5,600 steps/sec (700 instances/sec) holds flat
with no backlog.

Each instance is the 8-step `order-fulfilment` fork/join workflow: validate, a stock gate, two
parallel branches, an explicit combine, notify and audit. It runs in `LOCAL_ASYNC` mode. The bench
ramps the offered start rate and measures **probe sojourn**: the time a fresh instance takes from
`start()` to `COMPLETED`. The ceiling is the highest load at which sojourn stays bounded.

| Cloud SQL | sustained load | window | end-to-end latency |
|---|---|---|---|
| 8 vCPU | 4,000 steps/s (500/s) | 60s | flat **≈260ms** |
| 8 vCPU | **4,800 steps/s (600/s)**, the ceiling | 30s | ≈2.5s |
| 16 vCPU | 5,600 steps/s (700/s) | 30s | flat **≈260ms** |
| 16 vCPU | **7,200 steps/s (900/s)**, the ceiling | 60s | ≈2.5–3.7s |

![End-to-end latency over time at four sustained loads on Cloud SQL: 5,600 and 4,000 steps/sec stay flat near 260ms; 7,200 steps/sec on 16 vCPU holds at about 2.5 to 3.7 seconds and 4,800 steps/sec on 8 vCPU near 2.5 seconds.](/assets/img/bench-gcp-sojourn.svg)

![The ceiling follows the database: 4,800 durable step executions/sec (600 instances/sec) on an 8 vCPU Cloud SQL, 7,200 (900/s) on 16 vCPU, with flat 260ms latency up to 4,000 and 5,600 steps/sec respectively.](/assets/img/bench-gcp-ceiling.svg)

## What sets the ceiling

**The database sets the ceiling, not the server.** At the ceiling, Cloud SQL ran at ≈90% CPU
(8 vCPU) and ≈75% (16 vCPU). The server node stayed at 25–40% CPU and the workers had headroom.
Under load the same statements slowed 4–5×: a `wf_token` update went from 0.4ms to 2ms. Doubling
the database's vCPUs raised the ceiling 1.5×. Adding server nodes on the same database would not
raise it.

**Size the connection pool to the load.** With `WIGGLE_JDBC_POOL_SIZE=32` (the default is 10),
starts queued for a connection at ≈561/s while the server and database CPUs still had headroom.
One instance makes ≈45 SQL statements, so at 600/s about 25 connections are busy at once.
Raising the pool to 128 removed the limit.

## Environment

| | |
|---|---|
| Region | GCP `us-central1-a`. Everything is in one zone, on a private VPC. |
| Database | Cloud SQL Enterprise, PostgreSQL 16, zonal (no HA standby), 250 GB SSD, `db-custom-8-32768` and `db-custom-16-65536` |
| Server | 1 node, `c3-standard-8`, `WIGGLE_JDBC_POOL_SIZE=128`, default settings otherwise |
| Workers | own `c3-standard-8`: 4 processes × 256 slots, `LOCAL_ASYNC` batch 64 |
| Load generator | own `c3-standard-8`: `RateCeilingBench`, 256 submitter threads |
| Build | revision `dc7022c`, OpenJDK 21, fresh database |

A regional (HA) Cloud SQL instance adds a synchronous standby to every commit, so expect a lower
ceiling there.

## Reproduce it

The script provisions the environment, deploys a revision, runs the ladder, and collects
`pg_stat_statements`, per-VM CPU and a server JFR:

```bash
export GCP_PROJECT=<sandbox-project>
deploy/gcp/ceiling.sh up && deploy/gcp/ceiling.sh deploy && deploy/gcp/ceiling.sh run
deploy/gcp/ceiling.sh down
```

See [deploy/gcp/README.md](https://github.com/hadielmougy/wiggle/blob/main/deploy/gcp/README.md)
for every knob.
