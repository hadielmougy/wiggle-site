# Documentation

Wiggle is a **durable workflow engine** — and the control plane to shard it. You define a business
process as pure **topology** (named steps and how they chain, branch, and rejoin); Wiggle persists
every instance as tokens moving over that graph, so a process **survives restarts, retries, and
worker death** and resumes exactly where it left off. Steps are executed by **pull-based workers**
over gRPC — your services, in your processes, in your language.

## Where to start

| If you want to… | Read |
|---|---|
| Run something in the next ten minutes | [Onboarding & configuration](onboarding.md) |
| See every DSL operator in runnable code | [DSL cookbook](dsl-cookbook.md) |
| Split one flow's steps across many microservices | [Queues](queues.md) |
| Understand cells, epochs, and resharding | [Sharding & epochs](sharding-and-epochs.md) |
| Cut server round-trips for step-heavy flows | [Local execution](local-execution.md) |
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

Start embedded, end sharded — the same workflows run unchanged in all four postures:

| Mode | What it is |
|---|---|
| **Embedded** | `WiggleServer` inside your JVM, in-memory store — dev and tests |
| **Standalone** | one node, gRPC `:8080`, in-memory or a database |
| **Cluster** | several nodes sharing one database; a leader runs timers and recovery |
| **Cellular** | many cells (each its own DB + cluster) behind a Raft coordinator |

The [onboarding guide](onboarding.md) walks through each, including the ops console and the CLI.
