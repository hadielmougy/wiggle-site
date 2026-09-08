# Parallel fork / join

<div class="chips"><span>fork</span><span>combine</span><span>@Arm</span><span>@Context</span><span>RetryPolicy</span></div>

## The problem

Payment authorization and stock reservation don't depend on each other — running them
sequentially doubles your latency for no reason. But naive parallelism over shared state breeds
the worst kind of bug: two branches writing the same field, last-write-wins, invisible until
production.

## The topology

```java
Blueprint orders = Workflow.define("order-fulfilment")
        .step("validate")
        .gate("in-stock")                    // false ⇒ the instance ends cleanly
        .fork(
            Branch.of("payment", s -> s
                .step("authorise", RetryPolicy.exponential(5, Duration.ofMillis(100)))
                .step("capture")),
            Branch.of("shipping", s -> s
                .step("reserve-stock")
                .step("print-label")))
        .combine("merge")                    // mandatory — there is no implicit join
        .step("notify")
        .build();
```

## The handlers

```java
@Handlers("order-fulfilment")
class OrderHandlers {
    public Order   validate(Order o)     { return o.withStatus("VALIDATED"); }
    public boolean inStock(Order o)      { return o.quantity() > 0; }
    public Order   authorise(Order o)    { return o.withPaymentRef(gateway.auth(o)); }
    public Order   capture(Order o)      { return o.log("captured"); }
    public Order   reserveStock(Order o) { return o.withShipmentRef(wms.reserve(o)); }
    public Order   printLabel(Order o)   { return o.withTrackingLabel(courier.label(o)); }

    // Each @Arm parameter is one branch's final context; the pre-fork base arrives via
    // @Context (or ambiently via Step.base()). The return is the COMPLETE post-join context.
    public Order merge(@Context Order base, @Arm("payment") Order pay, @Arm("shipping") Order ship) {
        return base.withPaymentRef(pay.paymentRef())
                   .withShipmentRef(ship.shipmentRef())
                   .withTrackingLabel(ship.trackingLabel());
    }

    public Order notify(Order o)         { return o.withStatus("FULFILLED"); }
}
```

## Why this shape

- **Branches run on isolated context copies.** `authorise` cannot see what `reserve-stock` wrote,
  and vice versa — there is no shared mutable state to race on. Each branch transforms its own
  copy in peace.
- **The combine is mandatory and explicit.** The engine will not union, deep-merge, or
  last-write-wins your branches together. If two branches' results must become one state, *you*
  write the line of code that says how — which means the join semantics are visible in review,
  testable in isolation, and never surprising.
- **Retry policy is per step, in the topology.** `authorise` retrying five times with exponential
  backoff is a property of the graph, not something hidden in handler code — visible to anyone
  reading the definition, and to the ops console.
- **The gate is business logic, not an error.** `in-stock` returning `false` ends the instance
  cleanly; it isn't a failure and doesn't alarm.

## Variations

- An **effect arm** (`void` handler) contributes nothing to the combine — useful for a
  fire-and-forget audit branch running alongside real work.
- Fork inside a fork works; combines pair innermost-first.
- For a fan-out whose width is only known at runtime, use [dynamic fan-out](/patterns/fan-out/)
  instead of a fixed fork.
