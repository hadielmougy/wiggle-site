# Retries & failure isolation

<div class="chips"><span>RetryPolicy</span><span>gate</span><span>doWhile</span><span>leases</span></div>

## The problem

The payment gateway times out sometimes. The fraud service has a deploy window. A warehouse API
needs polling until a reservation settles. Failure handling scattered through business code turns
every handler into a try/catch labyrinth — and still loses work when the *worker itself* dies
mid-step.

## Three tools, three failure classes

### 1. Transient failures → a retry policy on the step

```java
.step("authorise", RetryPolicy.exponential(5, Duration.ofMillis(100)))
```

The handler just throws. The engine re-dispatches with exponential backoff, up to the cap; the
attempt number is visible to the handler (`Step.attempt()`) when behavior should differ on a
retry. The policy lives in the topology — reviewable, and shown on the console trace.

### 2. Business-level "stop" → a gate

```java
.step("validate")
.gate("in-stock")          // false ⇒ the instance ENDS CLEANLY — not an error, no alarm
.step("charge")
```

```java
public boolean inStock(Order o) { return o.quantity() > 0; }
```

A gate separates *"this order shouldn't proceed"* (a normal outcome) from *"something broke"*
(a failure). Instances ended by a gate complete without touching your error budget.

### 3. External dependency not ready → poll with `doWhile`

```java
Workflow.define("await-settlement")
    .doWhile("still-pending", b -> b
        .gate("not-cancelled")             // false short-circuits OUT of the loop entirely
        .step("poll")
        .sleep("backoff", Duration.ofSeconds(30)))   // parked server-side, no worker held
    .step("finish")
    .build();
```

```java
public boolean stillPending(Ctx c)  { return !c.ready(); }      // loop condition, after each pass
public boolean notCancelled(Ctx c)  { return !c.cancelled(); }
public Ctx     poll(Ctx c)          { return c.withStatus(api.check(c.ref())); }
```

## The failure class you don't handle: worker death

A claimed step carries a **lease**. If the worker dies mid-step — process kill, node loss,
network partition — the lease expires and the step is **redelivered to another worker**. No
handler code participates; at-least-once execution at the step level is the engine's contract.
Make handlers idempotent where the side effect demands it (an idempotency key on the payment
call), and the whole class disappears.

## Why this shape

- **Failure semantics live in the graph**, not in per-handler ceremony — a reviewer sees retry
  caps, gates, and loops in ten lines of topology.
- **A failed instance stops — or unwinds, if you declared it.** Steps marked `.compensate()`
  run their undos newest-first in a durable reverse pass when the instance fails; everything
  else just stops in place. See the [saga / compensation pattern](/patterns/saga/).
- **Sleeps park server-side.** A 30-second backoff (or a 3-day one) holds no worker; the timer
  survives restarts and fires once.
