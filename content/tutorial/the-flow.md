# The flow

A wiggle workflow is split in two, and the split is the whole design: a **topology** that says what
happens in what order, and **handlers** that say what each step does. This page writes the topology.
Nothing here runs any business logic — it names steps.

## The data

The workflow's context is an ordinary record. It is what gets persisted between steps, so it has to
be JSON-shaped: records, collections, primitives.

<!-- snippet: tutorial/records -->
```java
public record Item(String sku, BigDecimal price) {}

public record Order(String id, List<Item> items, BigDecimal total, String status) {
    Order withTotal(BigDecimal t) { return new Order(id, items, t, status); }
    Order withStatus(String s)    { return new Order(id, items, total, s); }
}
```

The `with…` helpers are just convenience: a step returns the **complete** next context, so handlers
build a new record rather than mutating one.

## The contract

Steps are declared as an interface. Nothing implements it yet — it exists so the compiler can check
that the steps fit together, and so the topology can name them with method references that survive a
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

Two signatures are worth pausing on.

`price` takes an **`Item`**, not an `Order`. Inside a `thenForEach`, each branch's whole context *is*
the element. If you need the order it came from, ask for it — that's what `@Context` does on `total`.

`total` takes the pre-fan-out `Order` **and** the collected results. Branches run on isolated copies
of the context, so nothing a branch writes reaches the shared context implicitly. The combine is the
only way results come back, which is why it is mandatory and why its return is the complete
post-join context.

## The topology

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

Reading it:

- **`thenApply`** — a step whose return becomes the new context.
- **`thenFilter`** — a *gate*. False ends the instance **successfully**; it is not an error and it
  raises no alarm. Use it for "this one doesn't apply", not for "this one broke".
- **`thenForEach(Order::items, …)`** — runtime fan-out, one isolated branch per element. The
  accessor gives both the context key (`items`) and the element type (`Item`), so renaming the record
  component carries the flow with it and a typo is a compile error.
- **`RetryPolicy.exponential(5, …)`** — retry belongs to the step it configures, passed right there.
  A step with no policy inherits the workflow default.
- **`.combine(s::total)`** — the mandatory rejoin.

`FlowSpec.define` returns a value; it has not talked to a server yet. Next: **[the
handlers](/tutorial/the-handlers/)**.
