# Dynamic fan-out (forEach)

<div class="chips"><span>forEach</span><span>combine</span><span>Step.base()</span><span>items-as-context</span></div>

## The problem

An order has *n* line items — price each one, in parallel, where *n* is only known at runtime. A
fixed `fork` can't express it, and hand-rolling it (start a child per item, poll for all of them,
merge) is exactly the fragile plumbing a workflow engine should own.

## The topology

```java
Workflow.define("price-order")
    .step("load-order")
    .forEach("charge-items", "items", b -> b     // one isolated branch per element of ctx["items"]
        .step("price"))
    .combine("collect")                          // receives the collected results
    .step("summarise")
    .build();
```

## The handlers

```java
@Handlers("price-order")
class PricingHandlers {
    public Order load(Map<String, Object> ctx) { return repo.load(ctx); }

    // The parameter IS the element — the element is the item's context. Scalars work too.
    public Priced price(LineItem line) {
        Order base = Step.base(Order.class);     // frozen pre-forEach context, read-only
        return new Priced(line.sku(), base.rate() * line.amount());
    }

    // The engine collects each item's FINAL value: List in order for a list input,
    // Map keyed like the input for a map input, Set for a set. You fold explicitly.
    public Order collect(@Context Order base, List<Priced> priced) {
        return base.withItems(priced)
                   .withTotal(priced.stream().map(Priced::amount).reduce(ZERO, BigDecimal::add));
    }

    public Order summarise(Order o) { return o.withStatus("PRICED"); }
}
```

## Why this shape

- **The element is the branch's context.** `price` receives a `LineItem`, returns a `Priced` —
  it *maps* the element, exactly like a `map()` over a collection, except each application is a
  durable, retryable, individually-leased step.
- **Shared state is readable, not writable.** The pre-loop context rides along ambiently
  (`Step.base()`, or a `@Context` parameter — your signature chooses), so per-item logic can read
  shared data with no possibility of racing on it.
- **Results collect in the input's shape.** A list input yields an ordered list; a map input a
  map under the same keys. The combine then decides what actually lands in the context — no
  implicit write-back of a thousand item results into shared state.
- **Empty input short-circuits.** No elements means the body *and* the combine are skipped —
  no special-casing in your handlers.

## Variations

- Pin one step of the body to a different worker pool:
  `b.step("price").step("render-thumbnail", "gpu")` — see [queues](/docs/queues/).
- Items can be maps or scalars; `Step.itemIndex()` / `Step.itemMapKey()` expose the element's
  position when the handler needs it.
- For a *fixed* set of differently-shaped branches, use [fork/join](/patterns/fork-join/) — fan-out
  is for homogeneous work over a collection.
