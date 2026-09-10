# Saga / compensation

<div class="chips"><span>compensate()</span><span>Compensable</span><span>Compensation</span><span>COMPENSATED</span></div>

## The problem

A booking flow reserves inventory, charges a card, then books a courier — and the courier API
rejects the order. The money is captured, the stock is held, and there is no transaction to roll
back: those side effects live in *other systems*. Distributed transactions don't exist here;
what exists is the **saga** — every forward step that touches the outside world pairs with an
undo, and when the flow fails, the undos run in reverse.

The hard part isn't running the undos. It's giving each undo the **data it needs**: by the time
the failure happens, later steps have replaced the context, and the `reservationRef` the undo
depends on may be long gone from the live state.

## The topology

The undo is **declared in the graph** — a reviewer sees which steps compensate in the topology,
not by hunting through handler code:

```java
Blueprint booking = Workflow.define("booking")
        .step("reserve-stock").compensate()      // has an undo
        .step("charge-card").compensate()        // has an undo
        .step("book-courier")                    // no undo: nothing external to unwind
        .build();
```

## The handlers

A compensable step's activity implements `Compensable` — the code that does the thing and the
code that undoes it live in **one class**, and the pairing is checked at bind time (a declared
`.compensate()` without a `Compensable` handler refuses to bind, and vice versa):

```java
@Handlers("booking")
class BookingHandlers {

    public Activity<Order> reserveStock() {
        class Reserve implements Activity<Order>, Compensable<Order> {
            public Order execute(Order o) {
                return o.withReservationRef(wms.reserve(o));
            }
            public void compensate(Compensation<Order> c) {
                wms.release(c.result().reservationRef());   // the step's OWN result snapshot
            }
        }
        return new Reserve();
    }

    public Activity<Order> chargeCard() {
        class Charge implements Activity<Order>, Compensable<Order> {
            public Order execute(Order o) {
                return o.withPaymentRef(gateway.capture(o));
            }
            public void compensate(Compensation<Order> c) {
                gateway.refund(c.result().paymentRef(),
                               idempotencyKey(c.input()));  // undo-only data from the INPUT snapshot
            }
        }
        return new Charge();
    }

    public Order bookCourier(Order o) { return o.withTracking(courier.book(o)); }
}
```

When `book-courier` exhausts its retries, the engine parks the instance `COMPENSATING` and runs
the reverse pass — `charge-card`'s undo first, then `reserve-stock`'s, each as a **real durable
task** through the normal claim/lease/retry machinery. When the log drains the instance settles
`COMPENSATED`, with the original failure preserved on it.

## Snapshots, not the live context

The compensator receives a `Compensation` carrier with **both context snapshots of its own
step**, captured at the step's completion:

- `result()` — the context **as this step left it**. The step's own products (`paymentRef`,
  `reservationRef`) are guaranteed present here, no matter what later steps replaced.
- `input()` — the context **as this step received it**. Restore-previous-value undos and
  undo-only data (an idempotency key derived from the input) read from here, so nothing has to
  be smuggled through the business context just to reach the undo.

This is forced by Wiggle's replace semantics: a step's return *replaces* the context, so the
latest context is simply the wrong input for an undo. The snapshots make the undo's data
contract explicit and durable.

## Go and Python parity

The same declaration and pairing rules, in each client's idiom:

```go
wf := wiggle.Graph{Name: "booking", Steps: []wiggle.Node{
    wiggle.Step{Name: "reserve-stock", Compensate: true},
    wiggle.Step{Name: "charge-card", Compensate: true},
    wiggle.Step{Name: "book-courier"},
}}

// on a RegisterHandlers struct: Compensate<Step> pairs with the step
func (h Handlers) ChargeCard(o wiggle.Context) (wiggle.Context, error) { ... }
func (h Handlers) CompensateChargeCard(c wiggle.Compensation) error {
    return gateway.Refund(c.Result["paymentRef"].(string))
}
```

```python
bp = Graph("booking", [
    Step("reserve-stock", compensate=True),
    Step("charge-card", compensate=True),
    Step("book-courier"),
])

class Handlers(wiggle.Handlers):
    workflow = "booking"
    def charge_card(self, o): ...
    def compensate_charge_card(self, c):        # compensate_<step> pairs with the step
        gateway.refund(c.result["paymentRef"])
```

A worker that serves a compensable step's forward handler without its compensator **refuses to
start** — the undo task lands on the same queue, and a worker that can do but not undo would
strand the reverse pass.

## When the undo itself fails

Compensators retry like any handler. One that exhausts its retries parks the instance
`COMPENSATION_FAILED` — loudly, with the step and undo sequence in the error. The one thing
worse than a stuck saga is a stuck saga reported as success; Wiggle refuses to pretend and
demands a human.

## Why this shape

- **The topology is the contract.** Which steps compensate is graph data — reviewable, versioned
  by content hash, visible on the trace — not a convention buried in handler internals.
- **Pairing is verified both ways at bind time**, in every client. A declared undo that isn't
  implemented, or an implemented undo that isn't declared, fails at worker start — not at 3 a.m.
  mid-reverse-pass.
- **Undos are durable tasks.** The reverse pass survives crashes, redeploys, and worker deaths
  exactly like the forward pass; nothing about compensation is best-effort.
- **At-least-once, like everything.** Make compensators idempotent — refund by an idempotency
  key, not blindly. The `input()` snapshot exists precisely so that key has somewhere to come
  from.
