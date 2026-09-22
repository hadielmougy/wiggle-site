# Deploying Wiggle on Kubernetes

Three deployment profiles, one image, one rule that makes all of them simple: **every bit of
workflow state lives in the database**. A Wiggle node holds nothing that matters in memory, so
"failover" is never a data question — it's only a question of how many nodes are serving and where
the pods come back.

Pick a profile:

| Profile | Shape | Pick it when |
|---|---|---|
| [A · Single server, active/passive](#a--single-server-activepassive) | 1 node; Kubernetes reschedules it | small services, first production deploy |
| [B · Cluster, active/active](#b--cluster-activeactive) | N nodes on one database, all serving | production HA, zero-downtime rollouts |

Deciding between A and B? There's a **[complete decision guide](/high-availability/)** —
mechanics, failure timelines, every trade-off dimension, and the full configuration reference
for both postures.

```mermaid
flowchart LR
  Q1{"need HA?"} -->|no| A["A · single server<br/>active/passive"]
  Q1 -->|yes| B["B · cluster<br/>active/active"]
```

Both profiles use the same image — `hadielmougy/wiggle:0.0.8` — specialised entirely by env
(`WIGGLE_ROLE=server | console`), and the same workflows: **moving between profiles
never changes a workflow definition or a worker.** Workers are not part of these manifests: they
are pull-based processes in *your* services (any language) that long-poll the server over gRPC —
they need egress to port 8080, nothing inbound.

---

## A · Single server, active/passive

The honest version of active/passive with Wiggle: **the database is the state, so the "passive"
node is simply the next pod.** You run one replica; when it dies or its node drains, Kubernetes
reschedules it, and the new pod resumes every in-flight instance from rows — timers, leases,
parked signals included. There is no standby process to keep warm and no replication to operate
beyond your database's own.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wiggle
spec:
  replicas: 1
  strategy: { type: Recreate }        # strict single-active; see the note below
  selector: { matchLabels: { app: wiggle } }
  template:
    metadata: { labels: { app: wiggle } }
    spec:
      containers:
        - name: wiggle
          image: hadielmougy/wiggle:0.0.8
          ports:
            - { containerPort: 8080, name: grpc }
            - { containerPort: 8090, name: health }
          env:
            - name: WIGGLE_NODE_NAME
              valueFrom: { fieldRef: { fieldPath: metadata.name } }
            - { name: WIGGLE_PORT, value: "8080" }
            - { name: WIGGLE_DASHBOARD_PORT, value: "8090" }   # /healthz probe endpoint
            - { name: WIGGLE_JDBC_URL, value: "jdbc:postgresql://postgres:5432/wiggle" }
            - { name: WIGGLE_JDBC_USER, value: "wiggle" }
            - name: WIGGLE_JDBC_PASSWORD
              valueFrom: { secretKeyRef: { name: wiggle-db, key: password } }
          readinessProbe:
            tcpSocket: { port: 8080 }
            initialDelaySeconds: 3
            periodSeconds: 3
          livenessProbe:
            httpGet: { path: /healthz, port: 8090 }
            initialDelaySeconds: 10
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata: { name: wiggle }
spec:
  selector: { app: wiggle }
  ports:
    - { name: grpc, port: 8080, targetPort: 8080 }
```

Point it at your managed Postgres (RDS, Cloud SQL, …). The schema creates and migrates itself on
startup (versioned, forward-only, under a cross-node advisory lock), so there is no migration job
to run.

**What failover looks like:** the pod dies → Kubernetes reschedules → the new pod reads where
every instance stands and continues. Steps that were leased to a worker when the node died are
redelivered when their lease expires (`WIGGLE_LEASE_MILLIS`, default 30s). Recovery time is pod
scheduling time, not data recovery time.

> **A note on `Recreate`.** It gives you a strict single-active posture — but it also means a gap
> during deploys. Because clustering in Wiggle is *just a shared database*, a rolling update that
> briefly runs two pods is completely safe: the two pods simply form a 2-node cluster for the
> overlap. If that's acceptable, drop the `strategy` block — and notice you're one line
> (`replicas: 3`) away from profile B. With Wiggle, active/active is not harder than
> active/passive; that's the point of the design. Weighing the two postures in depth →
> [the decision guide](/high-availability/).

**Ops console** (optional, separate Deployment — same image, different role):

```yaml
        - name: console
          image: hadielmougy/wiggle:0.0.8
          ports: [{ containerPort: 8090 }]
          env:
            - { name: WIGGLE_ROLE, value: "console" }
            - { name: WIGGLE_URL, value: "wiggle:8080" }
            - { name: WIGGLE_DASHBOARD_PORT, value: "8090" }
            - name: WIGGLE_DASHBOARD_PASSWORD
              valueFrom: { secretKeyRef: { name: wiggle-console, key: password } }
```

---

## B · Cluster, active/active

**Clustering is just a shared database.** Point several nodes at one Postgres and they form a
cluster: every node serves the gRPC API and hands out work; exactly one is elected leader for
clock-driven duties (timers, lease recovery, schedules). Kill any node — including the leader —
and the rest carry on; schedules fire exactly once even across leader failover. Clients need no
sticky sessions: any node answers any request, so a plain Service round-robins fine.

The only changes from profile A are the replica count, a rolling strategy, and two tuning knobs
worth setting under real load:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wiggle
spec:
  replicas: 3
  strategy:
    rollingUpdate: { maxUnavailable: 1, maxSurge: 1 }   # zero-downtime rollouts
  selector: { matchLabels: { app: wiggle } }
  template:
    metadata: { labels: { app: wiggle } }
    spec:
      containers:
        - name: wiggle
          image: hadielmougy/wiggle:0.0.8
          ports:
            - { containerPort: 8080, name: grpc }
            - { containerPort: 8090, name: health }
          env:
            - name: WIGGLE_NODE_NAME
              valueFrom: { fieldRef: { fieldPath: metadata.name } }   # distinct name per pod
            - { name: WIGGLE_PORT, value: "8080" }
            - { name: WIGGLE_DASHBOARD_PORT, value: "8090" }
            # Timer/housekeeping cadence: the defaults (1000ms tick, batch 100) cap timer
            # throughput at ~100/s and add up to 1s latency to every sleep. Under load:
            - { name: WIGGLE_POLL_INTERVAL_MILLIS, value: "200" }
            - { name: WIGGLE_HOUSEKEEPING_BATCH, value: "500" }
            # Drain mode: a sweep that fills its batch runs again immediately, so a timer/
            # schedule backlog clears in one tick instead of batch-per-tick (opt-in).
            - { name: WIGGLE_ADAPTIVE_HOUSEKEEPING, value: "true" }
            - { name: WIGGLE_JDBC_URL, value: "jdbc:postgresql://postgres:5432/wiggle" }
            - { name: WIGGLE_JDBC_USER, value: "wiggle" }
            - name: WIGGLE_JDBC_PASSWORD
              valueFrom: { secretKeyRef: { name: wiggle-db, key: password } }
            - { name: WIGGLE_JDBC_POOL_SIZE, value: "10" }   # × replicas ≤ your DB's limit
          readinessProbe:
            tcpSocket: { port: 8080 }
            initialDelaySeconds: 3
            periodSeconds: 3
          livenessProbe:
            httpGet: { path: /healthz, port: 8090 }
            initialDelaySeconds: 10
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata: { name: wiggle }
spec:
  selector: { app: wiggle }
  ports:
    - { name: grpc, port: 8080, targetPort: 8080 }
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: wiggle }
spec:
  minAvailable: 2
  selector: { matchLabels: { app: wiggle } }
```

**Sizing notes:**

- Node membership is heartbeat-based (`WIGGLE_HEARTBEAT_INTERVAL_MILLIS` 5s ×
  `WIGGLE_MISSED_HEARTBEATS` 3): a dead node's duties move to a peer within ~15s; its leased
  steps redeliver as leases expire.
- The **database is the shared resource** — size connections as `pool × replicas`, and treat
  retention as capacity: finished instances are purged after `WIGGLE_RETENTION_MILLIS`
  (default 24h). In our benchmarks, a database bloated with ~500k retained finished instances
  showed roughly **2× the latency** at the same load. Purge cadence is a capacity parameter,
  not housekeeping.
- One laptop-grade cluster sustains ~300 workflow starts/sec with sub-second completion —
  [full methodology](/performance/).

The console is identical to profile A (`WIGGLE_URL=wiggle:8080` — direct mode covers the whole
cluster, since every node sees the same database).

---

---

## Shared concerns (all profiles)

- **Probes.** Readiness: TCP on the gRPC port (8080 / 8099). Liveness: `GET /healthz` on
  `WIGGLE_DASHBOARD_PORT` — on a server node that port serves *only* the probe (the UI is
  the console process).
- **TLS / mTLS.** A mounted keystore + `WIGGLE_TLS_KEYSTORE`(+`_PASSWORD`) turns TLS on for gRPC
  and HTTP alike; adding a truststore on the server requires client certificates. Unset =
  plaintext, so terminate TLS somewhere before untrusted networks.
- **Secrets.** The manifests above read `WIGGLE_JDBC_PASSWORD` / dashboard passwords from
  Kubernetes Secrets; every `WIGGLE_*` var can also be supplied as a system property.
- **Resource limits.** Start servers at ~1 CPU / 1–2Gi and measure; the engine is a single JVM
  with modest memory needs. Enable `WIGGLE_MEMORY_SHEDDING_ENABLED=true` to shed worker polls
  under heap pressure instead of dying.
- **Upgrades.** Nodes are stateless; roll them freely. Workflow definitions are content-hash
  versioned — in-flight instances finish on the graph they started with, so deploying new
  definitions never needs a migration window.

The complete variable reference lives in [Onboarding & configuration](/docs/onboarding/).
