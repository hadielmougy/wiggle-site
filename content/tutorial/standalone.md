# 2 · Standalone server

The engine is **its own deployment** against its own database. Your services are clients that submit
work and workers that run it. This is the shape most teams end up in: one thing to scale and monitor,
many services around it, and no service that has to import everyone else's code.

If you have not read **[tutorial 1](/tutorial/embedded/)**, the flow and handlers below are explained
there in full — they are unchanged here, which is the point.

## 1. A database and a server

```bash
docker network create wiggle-net

docker run -d --name wiggle-db --network wiggle-net \
    -e POSTGRES_USER=wiggle -e POSTGRES_PASSWORD=wiggle -e POSTGRES_DB=wiggle \
    -p 5432:5432 postgres:16-alpine

docker run -d --name wiggle --network wiggle-net -p 8080:8080 \
    -e WIGGLE_JDBC_URL=jdbc:postgresql://wiggle-db:5432/wiggle \
    -e WIGGLE_JDBC_USER=wiggle -e WIGGLE_JDBC_PASSWORD=wiggle \
    hadielmougy/wiggle:0.0.6
```

The server migrates its own schema on first start. If your DBA owns the schema instead, run the
image once with `WIGGLE_MIGRATE_ONLY=true` and then run the app with `WIGGLE_SCHEMA_MODE=verify`,
which refuses to start rather than silently altering anything.

The whole configuration surface is environment variables — `WIGGLE_PORT`, `WIGGLE_NODE_NAME`,
`WIGGLE_LEASE_MILLIS`, `WIGGLE_RETENTION_MILLIS` and friends. See
[Onboarding](/docs/onboarding/) for the full list.

## 2. The flow and the handlers

Identical to tutorial 1 — the same `Orders.spec()` and the same `OrderHandlers`. Nothing about the
workflow knows where the server is running.

<!-- snippet: tutorial/topology -->
```java
public static FlowSpec spec() {
    return FlowSpec.define("orders", Order.class, OrderSteps.class, (f, s) -> f
            .thenApply(s::validate)
            .thenFilter(s::inStock)
            .thenForEach(Order::items, item -> item
                    .thenApply(s::price, RetryPolicy.exponential(5, Duration.ofMillis(100))))
            .combine(s::total)
            .thenApply(s::confirm));
}
```

## 3. The submitter

One process publishes the topology and starts instances. It holds **no handlers** — it does not need
the code that runs the steps on its classpath at all.

<!-- snippet: tut-standalone/submitter -->
```java
/** The submitter: registers the topology and starts instances. Owns no handlers. */
static String submit(String serverUrl) throws Exception {
    try (WiggleClient client = new WiggleClient(serverUrl)) {
        FlowSpec orders = Orders.spec();
        client.register(orders);
        return client.start(orders, new Orders.Order("A-1001",
                List.of(new Orders.Item("PEN", new BigDecimal("2.50")),
                        new Orders.Item("PAD", new BigDecimal("4.00"))),
                BigDecimal.ZERO, "NEW"));
    }
}
```

Registering is idempotent: the version is the content hash of the topology, so re-registering an
unchanged flow is a no-op and a changed one becomes a new version. Deploy the submitter as often as
you like.

## 4. The worker

A separate process brings the code. It never defines the flow — it fetches the graph by name and
binds its methods to the steps it finds.

<!-- snippet: tut-standalone/worker -->
```java
/** The worker: a separate process that brings the code. It never defines the flow. */
public static void main(String[] args) throws Exception {
    try (WiggleClient client = new WiggleClient("localhost:8080");
         Worker worker = new Worker(client, "worker-1")
                 .registerHandler(new OrderHandlers())
                 .start()) {

        System.out.println("worker-1 serving 'orders'; Ctrl-C to stop");
        Thread.currentThread().join();
    }
}
```

Run the submitter, then watch the worker price the order. Or run several workers — they compete for
steps, and each step goes to exactly one of them.

## Why the split is the point

The topology is registered once and lives on the server. Workers bring code. That means:

- **Services own steps, not workflows.** A payments service can serve `price` and nothing else;
  it needs no `Order` class from the shipping team. Give a step a queue and only workers subscribed
  to that queue will claim it — see [Queues](/docs/queues/) and
  [One flow, many services](/patterns/microservices/).
- **Deploys are independent.** Update a worker without touching the flow; update the flow without
  redeploying every worker, since the graph is data.
- **Scaling is per-step.** The pool serving the expensive step scales on its own.

## Prove it's durable

Start an instance, then `docker restart wiggle`, or kill a worker mid-step. The lease expires, the
step is handed to another worker, and the instance continues from the last completed step. Nothing
replays; the worker that picks it up did not have to be the one that started it.

## Look at it

```bash
docker run --rm -p 8090:8090 --network wiggle-net -e WIGGLE_ROLE=console \
    -e WIGGLE_URL=wiggle:8080 hadielmougy/wiggle:0.0.6
```

<http://localhost:8090> shows instances, their current node, context, retries and failures.

## Where to go next

- **[Tutorial 3 · Coordinator and cells](/tutorial/coordinated/)** — when one server and one
  database are no longer the right blast radius.
- **[Deploying on Kubernetes](/deployment/)** — the same thing with manifests and a Helm chart.
- **[Queues](/docs/queues/)** — route steps to the services that own them.
