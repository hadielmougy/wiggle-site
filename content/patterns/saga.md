# Saga / compensation

<div class="chips"><span>thenApplyCompensable</span><span>CompensableActivity</span><span>Compensation</span><span>COMPENSATED</span></div>

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
not by hunting through handler code. A compensable step is declared by its own signature: the
contract names it as a zero-argument factory returning a `CompensableActivity`, which is the same
shape the handler implements, so the two cannot drift.

```java
interface BookingSteps {
    CompensableActivity<Booking, Booking> reserveStock();   // has an undo
    CompensableActivity<Booking, Booking> chargeCard();     // has an undo
    Booking bookCourier(Booking b);                         // no undo: nothing external to unwind
}

FlowSpec booking = FlowSpec.define("booking", Booking.class, BookingSteps.class, (f, s) -> f
        .thenApplyCompensable(s::reserveStock)
        .thenApplyCompensable(s::chargeCard)
        .thenApply(s::bookCourier));
```

The declaration is the whole of it: `thenApplyCompensable` accepts nothing but a
`CompensableActivity` factory, and nothing else marks a node compensable. There is no second place
to say it, and so no way for the topology and the handler to disagree about whether an undo exists.

## The handlers

The compensator is not a separately-named handler: it is a **capability of the activity class**.
`CompensableActivity<A, B>` is just `Activity<A, B>` (which maps `A -> B` through `execute`) plus
`Compensable<A, B>` (which undoes it) — so the code that does the thing and the code that undoes it
live in **one class**, and the compiler checks the pairing rather than a string that can dangle:

```java
@ForFlow("booking")
class BookingHandlers {

    public CompensableActivity<Booking, Booking> reserveStock() {
        return new CompensableActivity<>() {
            public Booking execute(Booking b) {
                return b.withReservationRef(wms.reserve(b));
            }
            public void compensate(Compensation<Booking, Booking> c) {
                wms.release(c.result().reservationRef());   // the step's OWN result snapshot
            }
        };
    }

    public CompensableActivity<Booking, Booking> chargeCard() {
        return new CompensableActivity<>() {
            public Booking execute(Booking b) {
                return b.withPaymentRef(gateway.capture(b));
            }
            public void compensate(Compensation<Booking, Booking> c) {
                gateway.refund(c.result().paymentRef(),
                               idempotencyKey(c.input()));  // undo-only data from the INPUT snapshot
            }
        };
    }

    public Booking bookCourier(Booking b) { return b.withTracking(courier.book(b)); }
}
```

An activity maps `A -> B` like any other step, so a compensable step may change the context type —
`CompensableActivity<Order, Payment>` takes an `Order` and returns a `Payment`. Its undo then
receives a `Compensation<Order, Payment>`, the two snapshots being of different types, which is
precisely why they are named accessors rather than two same-typed positional parameters.

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
