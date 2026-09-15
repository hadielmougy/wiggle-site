# Run it

Three things have to happen: the topology gets **registered**, a **worker** binds the handlers, and
an **instance** is started.

<!-- snippet: tutorial/main -->
```java
public static void main(String[] args) throws Exception {
    try (WiggleClient client = new WiggleClient("localhost:8080")) {
        FlowSpec orders = spec();
        client.register(orders);                        // publish the topology

        try (Worker worker = new Worker(client, "worker-1")
                .registerHandler(new OrderHandlers())   // bind the code that runs the steps
                .start()) {

            Order order = new Order("A-1001",
                    List.of(new Item("PEN", new BigDecimal("2.50")),
                            new Item("PAD", new BigDecimal("4.00"))),
                    BigDecimal.ZERO, "NEW");

            String id = client.start(orders, order);
            InstanceView done = client.awaitCompletion(id, Duration.ofSeconds(30));

            System.out.println(done.status() + " " + done.context());
        }
    }
}
```

With the server container running, you should see:

```text
COMPLETED {"id":"A-1001","items":[{"sku":"PEN","price":3.00},{"sku":"PAD","price":4.80}],
           "total":7.80,"status":"CONFIRMED"}
```

`2.50` and `4.00` each picked up 20% in their own branch, and the combine summed them to `7.80`.

## What just happened

Registering **published a graph**, not your code. The server stores nodes and edges keyed by name,
with a version that is the content hash of the topology — change the flow and you get a new version;
change nothing and re-registering is a no-op.

Starting an instance created a durable row. From there the **server drives**: it hands the worker one
step at a time, the worker runs the matching method and hands back the new context, and the server
persists it before dispatching the next. There is no replay and no determinism rule, because your
code is never re-executed to rebuild state — the state *is* the stored context.

The fan-out is the same idea. The server read `items` from the context, spawned a branch per element
with the element as that branch's context, and held a join until all of them landed.

## Prove it's durable

While the flow is waiting, kill the worker — `Ctrl-C`, or `kill -9` if you want to be rude about it.
Start it again. The lease on the in-flight step expires, the server hands it to the new worker, and
the instance carries on from the step after the last one that completed. Nothing replays.

Add a `Thread.sleep(20_000)` inside `price` if you need a window wide enough to do it by hand.

## Look at it

```bash
docker run --rm -p 8090:8090 -e WIGGLE_ROLE=console \
    -e WIGGLE_URL=host.docker.internal:8080 hadielmougy/wiggle:0.0.4
```

Open <http://localhost:8090> for instances, their current node, context, retries and failures.

## Where to go next

- **[Cookbook](/docs/cookbook/)** — eight flows covering every operator, each one a test the project
  runs.
- **[Saga / compensation](/patterns/saga/)** — give `price` an undo, so a failure later unwinds it.
- **[Parallel fork / join](/patterns/fork-join/)** — fan out over *different* work, not a collection.
- **[Queues](/docs/queues/)** — run `price` on a pool of its own by adding one argument.
- **[Onboarding](/docs/onboarding/)** — PostgreSQL, versioning, workers, configuration.

Two changes worth making to this flow yourself, in order: move `price` onto its own queue (one
argument), then make it compensable (one type change in the contract). Both are single-line edits
from where you are now, and they are the two things most real flows need next.
