# One flow, many services

<div class="chips"><span>queues</span><span>defaultQueue</span><span>polyglot workers</span><span>pull-based</span></div>

## The problem

The order flow touches four teams: validation lives with the orders service, charging with
payments, receipt rendering with a GPU pool, email with notifications. One process, four
codebases, four deploy cadences — and nobody wants a broker between them or a central service
that imports everyone's code.

## The shape

Each step names a **queue**; each service runs a worker subscribed only to its queues:

```java
Blueprint orders = Workflow.define("orders")
        .step("validate", "orders")            // queue: orders service
        .step("charge", "payments")            // queue: payments service
        .step("render-receipt", "gpu")         // queue: the GPU pool
        .effect("email", "notify")             // queue: notifications
        .build();
```

Four separate processes — deployed, scaled, and owned independently:

```java
// payments-service (Java)
new Worker(client, "payments-1").register(orders)
        .handlers(new PaymentHandlers())        // only charge() matches a step it serves
        .start();
```

```go
// notifications-service (Go) — same instance, different language
w := wiggle.NewWorker(client, "notify-1",
    wiggle.Register(orders), wiggle.Handlers(NotifyHandlers{}))
```

The server dispatches each step to its queue; whichever worker serves that queue pulls it. The
instance's durable state stays in one place — each service sees the full context on its steps and
returns the next context.

## Why this shape

- **No broker, no choreography drift.** The graph *is* the source of truth for the end-to-end
  process — not an emergent property of who publishes which event. When the flow changes, one
  definition changes, and the console shows the real, current shape.
- **Workers pull; nothing dials into your services.** Long-polling gRPC means no inbound
  connectivity, no service mesh requirement, and backpressure by construction — a slow GPU pool
  queues its own steps without stalling the payments team.
- **Unserved steps just wait.** Deploying the flow before every team is ready is fine: steps for
  a queue nobody serves sit leased-less until a worker shows up. Rolling deploys of one service
  never lose work — leases expire and steps redeliver.
- **Polyglot by name-matching.** Binding is activity-name over the graph, so the language of each
  worker is invisible to the others — a Java flow can grow a Python step tomorrow.

## Variations

- `defaultQueue("cpu")` sets the workflow-wide default; per-step queue args override it — handy
  inside `forEach` bodies where one step needs the GPU pool.
- Queue-lag monitoring warns when a queue isn't draining (`WIGGLE_QUEUE_LAG_WARN_MILLIS`) —
  usually a service that forgot to deploy its worker.
- The [queues doc](/docs/queues/) walks the full end-to-end with diagrams.
