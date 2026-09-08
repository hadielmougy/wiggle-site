# Why Wiggle — the workflow as data, not code

Durable execution — the promise that a long-running business process survives crashes, restarts,
and redeployments, resuming exactly where it left off — has largely converged on one
implementation strategy: **event-sourced replay**. Engines in the Temporal/Cadence lineage persist
a history of events for each workflow; to make progress after a crash, a worker *re-executes the
workflow function from the beginning*, feeding recorded results back into it until the code
catches up with history.

It's a genuinely elegant trick, and it buys enormous expressiveness. But it has a price every
operating team eventually pays.

## The determinism tax

For replay to work, the workflow function must be **deterministic**: given the same history, it
must make exactly the same decisions, in exactly the same order, every time. That outlaws — inside
workflow code — random numbers, clock reads, iteration over unordered collections, config lookups,
library calls that might change behavior between versions, and, most painfully, *ordinary code
changes*. Deploying a modified workflow while instances are in flight requires version-patching
APIs and discipline, because the new code must still replay old histories faithfully.

The failure mode is what makes it a tax rather than a fee: **non-determinism does not fail at the
point of the mistake**. The workflow runs fine — until a worker somewhere replays it and the
re-execution diverges from history. The bug detonates during recovery, in production, possibly
weeks after it was introduced, in a workflow that "worked in every test."

The question worth asking: what exactly is being replayed, and why? The answer is *control flow*.
The engine replays your code because your code is the only representation of the workflow's
structure it has. Which suggests an alternative: **give the engine the structure directly.**

## Wiggle's bet: the graph is the workflow

A business process is described as a **graph** — named steps and how they chain, branch, and
rejoin — and that graph, not any function, is what the server owns:

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
        .combine("merge")                    // branches rejoin at an explicit merge step
        .step("notify")
        .build();
```

Nothing in that snippet executes. `build()` compiles a graph, and registering it ships the graph
to the server as data. A running instance is a set of **tokens** positioned on the graph, in the
spirit of a Petri net — and every token is a row in a database.

Recovery, in this model, is almost embarrassingly boring. There is no history to replay and no
function to re-execute, because the engine never lost the state in the first place — the state
*is* the rows. A crashed server restarts and reads where every instance stands. A crashed worker
is handled by **leases**: when a worker dies mid-step, the lease expires and the step is
redelivered. Execution is at-least-once at the step level, dispatch is exactly-once, and **no code
anywhere is subject to a determinism contract** — because no code is ever executed twice for the
engine's benefit.

Handlers are ordinary methods matched to the graph **by name**. They can use clocks, randomness,
any library. They can be redeployed at will. And because binding is by activity name over a
language-neutral graph, the same workflow's steps can be served by **Java, Go, and Python workers
simultaneously**.

## What it costs — stated plainly

**Your control flow is bounded by the DSL's operators.** Wiggle's vocabulary — sequential steps,
gates, exclusive choice, parallel fork/combine, dynamic fan-out over a collection, timers,
external signals with deadlines and escalation, sub-workflows, do-while loops — covers a large
share of real business processes. It does not cover all of them. If your orchestration logic is
genuinely algorithmic — control flow computed at runtime in ways no fixed operator set expresses —
then a replay engine's Turing-complete workflow code is the right tool, and its determinism tax is
the fair price.

That's the honest framing: replay engines make *code* durable and tax it with determinism; graph
engines make *data* durable and tax it with a vocabulary. Neither tax is avoidable. You choose the
one your workloads can afford.

## Explicitness as a design principle

Once state transitions are first-class, you must decide *exactly* what each one means — and every
softness in that definition becomes a bug factory. Wiggle's rules are strict:

- **A step's return replaces the state.** Not a delta, not a patch; keys the handler omits are
  gone. There is no diff-and-merge machinery anywhere in step execution, so there is never a
  question about what the state is after a step: it is what the handler returned.
- **Parallel branches never merge implicitly.** Each fork branch runs on an isolated copy of the
  context; siblings cannot see each other's writes. The only path back to shared state is the
  **mandatory combine step**. An earlier version offered a "default union" that folded disjoint
  branch writes automatically — it was removed deliberately, because an automatic merge is a
  decision the engine makes silently on your behalf, and last-write-wins races are exactly the
  class of bug that hides until production.
- **Dynamic fan-out maps elements.** `forEach` spawns one isolated branch per element; *the
  element itself is that branch's context*. The engine collects final values (a list for a list,
  a map keyed like the input for a map) and hands the collection to — again — an explicit combine.

The through-line: **in a data-first engine, the state transition rules are the product.** Every
place an implicit behavior became an explicit one, a category of "why does my context look like
this?" question disappeared.

## Versioning without patch APIs

A definition's version *is the content hash of its graph*. Re-registering an identical graph is a
no-op; registering a changed one creates a new version, and in-flight instances continue on the
version they started with — both graphs coexist in the database. No `patched()` calls, no version
branches inside workflow code, no migration windows.

## The second bet: cells instead of one big cluster

Wiggle's unit of scale is the **cell**: a namespace maps to one or more cells, and each cell is a
complete, independent deployment — its own server cluster and, crucially, *its own database*. A
small Raft-backed coordinator assigns work across cells by consistent hashing over **epochs**:
publishing a new shard-to-cell ring is an epoch bump; new instances follow the new ring while
in-flight instances finish where they live, so **resharding never migrates data**. Routing is
directory-free because each instance id embeds its namespace, epoch, and shard
(`orders.e0.s3.01J…`) — any party can compute the owning cell from the id alone.

The operational meaning is blast-radius isolation of a kind logical namespaces cannot offer:
tenant A's database melting down cannot touch tenant B's, because they do not share one.

## Choosing

If your processes are expressible as steps, branches, waits, and fan-outs — and in our experience
the overwhelming majority of order flows, onboarding pipelines, approval chains, and document
processes are — a data-first engine gives you durable execution with no determinism contract,
trivially redeployable handlers, polyglot workers, content-hash versioning, and an engine small
enough to read in an afternoon and embed in a test. If your orchestration is irreducibly
algorithmic, pay the replay tax knowingly and take the expressiveness.

The deeper lesson generalizes: **when a system replays code to reconstruct state, every property
of that code becomes a correctness constraint.** Moving the authoritative representation out of
code and into data shrinks the constrained surface to a vocabulary you control — and makes
everything the engine does to your state something you can point at, name, and test.

---

*Ready to try it? Start with the [docs](/docs/) or copy a shape from the
[patterns library](/patterns/).*
