# 1 · Embedded server

The engine runs **inside your own JVM**, against a database you already operate. One process, one
`main` method, no extra deployment — and the workflows are just as durable as in the other two
tutorials, because durability comes from the database, not from where the server runs.

Choose this when workflows are an implementation detail of one service. Outgrow it and tutorial 2 is
the same code with the server moved out.

## 1. A database

```bash
docker run --rm -e POSTGRES_USER=wiggle -e POSTGRES_PASSWORD=wiggle \
    -e POSTGRES_DB=wiggle -p 5432:5432 postgres:16-alpine
```

Any PostgreSQL will do; the server creates and migrates its own schema on first start.

## 2. The dependencies for hosting the engine

Embedding means you run the server, so add the server-side modules alongside the client:

```kotlin
dependencies {
    implementation(platform("sh.wiggle:wiggle-bom:0.0.6"))
    implementation("sh.wiggle:wiggle-client")
    implementation("sh.wiggle:wiggle-postgres")
}
```

Storage selection is an explicit factory rather than classpath discovery — no `ServiceLoader`, no
`META-INF/services`. `PostgresStorageFactory` is the mapping the project ships (`jdbc:postgresql:`,
`jdbc:h2:` for local runs, no URL at all for in-memory) and it arrives with `wiggle-postgres`, so
that one dependency is the whole requirement. `StorageFactory` is a functional interface, so an app
wanting a different mapping — its own dialect, or a wrapper that instruments the store — passes a
lambda instead.

## 3. The flow

<!-- snippet: tutorial/records -->
```java
public record Item(String sku, BigDecimal price) {}

public record Order(String id, List<Item> items, BigDecimal total, String status) {
    Order withTotal(BigDecimal t) { return new Order(id, items, t, status); }
    Order withStatus(String s)    { return new Order(id, items, total, s); }
}
```

Steps are declared as an interface. Nothing implements it yet — it exists so the compiler can check
the steps fit together, and so the topology can name them with method references that survive a
rename.

<!-- snippet: tutorial/contract -->
```java
public interface OrderSteps {
    Order   validate(Order o);
    boolean inStock(Order o);                              // a gate: false ends the flow cleanly
    Item    price(Item item);                              // the element IS the branch's context
    Order   total(@Context Order base, List<Item> priced);  // the mandatory combine
    Order   confirm(Order o);
}
```

`price` takes an **`Item`**, not an `Order`: inside a `thenForEach`, each branch's whole context *is*
the element. `total` takes the pre-fan-out `Order` **and** the collected results, because branches
run on isolated copies and the combine is the only way results come back.

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

- **`thenFilter`** is a *gate*: false ends the instance **successfully**. It is not an error and
  raises no alarm — use it for "this one doesn't apply", not "this one broke".
- **`thenForEach(Order::items, …)`** fans out one isolated branch per element. The accessor gives
  both the context key and the element type, so renaming the record component carries the flow with
  it and a typo is a compile error.
- **`RetryPolicy.exponential(5, …)`** belongs to the step it configures, passed right there.

## 4. The handlers

<!-- snippet: tutorial-handlers/handlers -->
```java
@ForFlow("orders")                                  // which flow these steps belong to
public class OrderHandlers implements OrderSteps {  // implementing the contract is optional,
                                                    // but then the compiler checks every signature

    @Override public Order validate(Order o) {
        if (o.items().isEmpty()) throw new IllegalArgumentException("empty order " + o.id());
        return o.withStatus("VALIDATED");
    }

    @Override public boolean inStock(Order o) {
        return o.items().size() <= 50;              // false ends the instance cleanly, not as a failure
    }

    @Override public Item price(Item item) {
        return new Item(item.sku(), item.price().multiply(new BigDecimal("1.20")));   // + VAT
    }

    @Override public Order total(@Context Order base, List<Item> priced) {
        return base.withTotal(priced.stream().map(Item::price)
                .reduce(BigDecimal.ZERO, BigDecimal::add));
    }

    @Override public Order confirm(Order o) {
        return o.withStatus("CONFIRMED");
    }
}
```

Binding is **by method name**: `validate` serves the step named `validate`, folded canonically, so a
step named `in-stock` and a method `inStock` are the same thing. Use `@Handles("step-name")` when a
method name cannot match. `@Context` must be repeated on the implementation — parameter annotations
are not inherited, and the binder reads the method that actually runs.

## 5. Put it together

<!-- snippet: tut-embedded/main -->
```java
public static void main(String[] args) throws Exception {
    ServerConfig config = ServerConfig.fromEnvironment()
            .withStorage("jdbc:postgresql://localhost:5432/wiggle", "wiggle", "wiggle", 8)
            .withPort(8080);

    try (WiggleServer server = new WiggleServer(config, new PostgresStorageFactory()).start();
         WiggleClient client = new WiggleClient(server.baseUrl())) {

        FlowSpec orders = Orders.spec();
        client.register(orders);

        try (Worker worker = new Worker(client, "worker-1")
                .registerHandler(new OrderHandlers())
                .start()) {

            String id = client.start(orders, new Order("A-1001",
                        List.of(new Item("PEN", new BigDecimal("2.50")),
                                new Item("PAD", new BigDecimal("4.00"))),
                        BigDecimal.ZERO, "NEW"));

            InstanceView done = client.awaitCompletion(id, Duration.ofSeconds(30));
            System.out.println(done.status() + " " + done.context());
        }
    }
}
```

```text
COMPLETED {"id":"A-1001","items":[{"sku":"PEN","price":3.00},{"sku":"PAD","price":4.80}],
           "total":7.80,"status":"CONFIRMED"}
```

**Order matters on one line only:** register before the worker starts. A worker binds its handlers
to the registered graph at `start()`, so a worker that starts first has nothing to bind to and says
so. (If you would rather it wait, `WorkerOptions.withAwaitRegistration` does that.)

## What just happened

Registering published a **graph** — nodes and edges keyed by name, versioned by the content hash of
the topology. Starting an instance wrote a durable row. From there the server drives: it hands the
worker one step at a time, the worker runs the matching method and hands back the new context, and
the server persists it before dispatching the next. No replay, no determinism rules — your code is
never re-executed to rebuild state, because the state *is* the stored context.

The engine being in your process changes none of that. It is the same server, the same database
rows, the same recovery.

## Prove it's durable

Put a `Thread.sleep(20_000)` in `price`, run it, and kill the JVM while it waits. Start it again:
the lease on the in-flight step expires, the step is handed out afresh, and the instance carries on
from the last step that completed. Nothing replays.

## Where to go next

- **[Tutorial 2 · Standalone server](/tutorial/standalone/)** — the same flow with the engine as its
  own deployment.
- **[Cookbook](/docs/cookbook/)** — eight flows covering every operator, each one a test the project
  runs.
- **[Saga / compensation](/patterns/saga/)** — give `price` an undo so a later failure unwinds it.
