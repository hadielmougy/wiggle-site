# Go & Python clients

Wiggle's wire protocol is language-neutral gRPC, and step binding is **by activity name over the
graph** — so the same workflow's steps can be served by Java, Go, and Python workers
simultaneously. One instance, three languages, no shared SDK semantics beyond the proto.

Both clients are idiomatic, not transliterations of the Java API. Both live in their own
repositories with their own examples and test suites:

- **Go** — [github.com/hadielmougy/wiggle-go](https://github.com/hadielmougy/wiggle-go)
- **Python** — [github.com/hadielmougy/wiggle-python](https://github.com/hadielmougy/wiggle-python)

## Go

Workers are structs; the handler surface is explicit interfaces (`Activity`, `ItemActivity` for
`forEach` bodies) — no reflection magic beyond name matching, no goroutine-local state:

```go
type OrderHandlers struct{}

func (OrderHandlers) Workflow() string { return "order-fulfilment" }

func (OrderHandlers) Validate(ctx wiggle.Context) (wiggle.Context, error) {
    ctx["status"] = "VALIDATED"
    return ctx, nil            // the return REPLACES the context
}

func (OrderHandlers) InStock(ctx wiggle.Context) (bool, error) {   // a gate
    return ctx["quantity"].(float64) > 0, nil
}

// forEach body: the element is the item's context; base comes in explicitly
func (OrderHandlers) Price(base wiggle.Context, item any) (any, error) {
    return price(base, item), nil
}
```

```go
w := wiggle.NewWorker(client, "worker-go",
    wiggle.Register(orderBlueprint), wiggle.Handlers(OrderHandlers{}))
w.Start(ctx)
```

## Python

Handler classes are plain objects — public methods are steps, matched by case-folded name; the
**return annotation** picks the step kind (`-> bool` = gate, `-> None` = effect, anything else a
task whose return replaces the context):

```python
class OrderHandlers:
    workflow = "order-fulfilment"

    def validate(self, ctx):
        return {**ctx, "status": "VALIDATED"}       # replaces the context

    def in_stock(self, ctx) -> bool:                # a gate
        return ctx["quantity"] > 0

    def price(self, item):                          # forEach body: the element IS the context
        base = wiggle.step.base()                   # frozen pre-loop context, read-only
        return base["rate"] * item["amount"]

    def collect(self, ctx) -> dict:                 # the explicit combine
        return {**wiggle.step.base(), "priced": ctx["charge-items"]}
```

```python
worker = wiggle.Worker(client, "worker-py")
worker.register(order_blueprint, OrderHandlers())
worker.start()
```

## Shared semantics

All three clients honour the same contracts, because the contracts live in the graph and the
engine, not the SDK:

- a task's return **replaces** the context (`None`/`null` leaves it untouched);
- fork branches are isolated; the **combine is mandatory and explicit**;
- `forEach` maps elements — the element is the item's context; results collect into a
  list/map/set shaped like the input, handed to the combine;
- gates end the instance cleanly on `false`; effects never touch the context;
- retries, leases, timers, and signals are engine-side and identical everywhere.
