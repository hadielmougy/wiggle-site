# Human-in-the-loop approval

<div class="chips"><span>awaitSignal</span><span>deadline + escalation</span><span>choose</span><span>effect</span></div>

## The problem

An expense report needs a manager's decision. The manager might act in a minute or a week — or
never. Holding a worker thread (or any process resource) for that wait is absurd; forgetting the
"or never" case is how requests rot in queues forever.

## The topology

```java
Workflow.define("expense-approval")
    .step("submit")
    .awaitSignal("manager-approval", Duration.ofHours(48),
        esc -> esc.step("auto-escalate"))            // runs only if the deadline passes
    .choose(
        Case.when("was-escalated", b -> b.effect("notify-director")),
        Case.otherwise("approved-path", b -> b.step("pay-out")))
    .build();
```

## The handlers

```java
@Handlers("expense-approval")
class ExpenseHandlers {
    public Expense submit(Expense e)       { return e.withState("PENDING_APPROVAL"); }

    // deadline branch: nobody acted within 48h
    public Expense autoEscalate(Expense e) { return e.escalated(true); }

    public boolean wasEscalated(Expense e) { return e.isEscalated(); }   // choose guard
    public void    notifyDirector(Expense e) { mail.director(e); }        // effect: no state change
    public Expense payOut(Expense e)       { return e.withState("PAID"); }
}
```

Delivering the decision is one client call, from any process that knows the instance id:

```java
client.signal(instanceId, "manager-approval", Map.of("decision", "approved", "by", "sam"));
```

## Why this shape

- **The instance parks; nothing is held.** A signal wait is a token at rest in the database — no
  worker, no thread, no lease. A million parked approvals cost a million rows, not a million
  threads.
- **The deadline is part of the topology.** "48 hours, then escalate" is visible in the graph and
  survives every restart — the timer is server-side and leader-managed, firing exactly once even
  across failover.
- **Exactly one of delivery or escalation happens.** The flow rejoins after the wait either way,
  so the downstream `choose` reads whichever field the branch that ran actually set. No race
  between the human and the clock.
- **The signal payload merges into the context** — the one place external input enters state — so
  `pay-out` can read `decision` and `by` like any other field.

## Variations

- Chain waits for multi-level approval: manager → finance, each with its own deadline.
- The escalation branch can itself `awaitSignal` (director approval with a stricter deadline).
- The ops console can deliver signals manually — useful for support interventions — and shows
  every parked wait on the instance trace.
