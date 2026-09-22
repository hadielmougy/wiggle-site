# Documentation

Wiggle is a **durable workflow engine**: a JAR and a database. You define a business
process as pure **topology** (named steps and how they chain, branch, and rejoin); Wiggle persists
every instance as tokens moving over that graph, so a process **survives restarts, retries, and
worker death** and resumes exactly where it left off. Steps are executed by **pull-based workers**
over gRPC — your services, in your processes, in your language.

## Where to start

| If you want to… | Read |
|---|---|
| Run something in the next ten minutes | [Onboarding & configuration](onboarding.md) |
| See every operator in runnable code | [Cookbook](cookbook.md) |
| Split one flow's steps across many microservices | [Queues](queues.md) |
| Cut server round-trips for step-heavy flows | [Local execution](local-execution.md) |
| Check runs your services execute themselves, for conformance and bottlenecks | [Observed execution](observed-execution.md) |
| Write workers in Go or Python | [Go & Python clients](clients.md) |
| Copy a working shape for a real process | [The patterns library](/patterns/) |

## The mental model in five sentences

1. A **workflow definition** is a compiled graph — data the server owns, versioned by the content
   hash of the graph. There is no workflow *code* on the server, so there is **no replay and no
   determinism contract**.
2. A **running instance** is a set of tokens positioned on that graph (in the spirit of a Petri
   net), each token a database row. Recovery is reading the rows.
3. **Handlers** are plain methods in your services, matched to steps **by name**. A method's
   signature picks its kind: `boolean` return = gate, `void` = effect, anything else = a task whose
   return **replaces** the context.
4. **Nothing merges implicitly.** Fork branches run on isolated context copies and rejoin only
   through an explicit combine step; `forEach` maps elements and hands you the collected results.
5. **Workers pull.** They long-poll queues over gRPC with lease-based claims — no inbound
   connectivity to your services, backpressure by construction, at-least-once execution with
   exactly-once dispatch.

## Running modes

Start embedded, grow into a cluster — the same workflows run unchanged in all three postures:

| Mode | What it is |
|---|---|
| **Embedded** | `WiggleServer` inside your JVM, in-memory store — dev and tests |
| **Standalone** | one node, gRPC `:8080`, in-memory or a database |
| **Cluster** | several nodes sharing one database; a leader runs timers and recovery |

The [onboarding guide](onboarding.md) walks through each, including the ops console.

## Execution modes

Where a step runs is a property of the workflow, not of the deployment. A worker-run flow picks
one of three with `executeInServer()`, `executeInLocalSync()` or `executeInLocalAsync()`; the
fourth is stamped by the observer that publishes a flow, never by the spec:

| Mode | Who runs the step | What the server does |
|---|---|---|
| `SERVER` | a worker, one round-trip per step | dispatches every step, commits every completion |
| `LOCAL_SYNC` / `LOCAL_ASYNC` | a worker, chaining same-queue steps | commits per step, or once per batch — [local execution](local-execution.md) |
| `OBSERVED` | your own service, on its own thread | dispatches nothing; checks each reported run against the topology and keeps its timings — [observed execution](observed-execution.md) |

Every mode lands in the same **Performance** view of the console: per-step p50/p95 by the
handler's own clock, queue wait for worker-run steps, and the anomalies of observed runs.

![The console's Performance tab: the slowest step ringed on the diagram, the step table ranked by p95, and the anomaly list below.](/assets/img/console-performance.png)
