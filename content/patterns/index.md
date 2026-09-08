# Patterns

Working shapes for real processes — each pattern is a **topology + handlers you can copy**, with
the reasoning for why the shape looks the way it does. All of them run against an embedded server
in one JVM, so every pattern is testable before it's deployed.

<div class="grid" markdown>
<a class="cardlink" href="/patterns/fork-join/"><div class="card"><h3>⑂ Parallel fork / join</h3>
<p>Run independent branches concurrently on isolated state; rejoin through an explicit,
hand-written combine. The foundation everything else builds on.</p></div></a>
<a class="cardlink" href="/patterns/approval/"><div class="card"><h3>✋ Human-in-the-loop approval</h3>
<p>Park the instance on a signal — no worker held — with a deadline that escalates when nobody
acts, and a branch on which of the two happened.</p></div></a>
<a class="cardlink" href="/patterns/fan-out/"><div class="card"><h3>⇶ Dynamic fan-out</h3>
<p>One isolated branch per element of a runtime collection; results collected in input shape and
folded by an explicit combine.</p></div></a>
<a class="cardlink" href="/patterns/retries/"><div class="card"><h3>↻ Retries & failure isolation</h3>
<p>Exponential backoff per step, gates for business-level "stop cleanly", and poll-until-ready
loops for external dependencies.</p></div></a>
<a class="cardlink" href="/patterns/scheduled/"><div class="card"><h3>⏰ Cron & scheduled work</h3>
<p>Server-side cron and interval schedules with exactly-once firing across leader failover — no
external scheduler.</p></div></a>
<a class="cardlink" href="/patterns/microservices/"><div class="card"><h3>🧵 One flow, many services</h3>
<p>Route each step to a queue; separate services (in separate languages) each serve only their
steps of the same durable instance.</p></div></a>
<a class="cardlink" href="/patterns/cells/"><div class="card"><h3>🧫 Per-tenant isolation</h3>
<p>Give a tenant its own cell — database and cluster — behind one coordinator, with
zero-migration resharding when load grows.</p></div></a>
</div>

## How to read a pattern

Every page follows the same skeleton:

1. **The problem** — when you reach for this shape.
2. **The topology** — the graph, in the DSL.
3. **The handlers** — plain methods matched by name; the signature picks the step kind.
4. **Why this shape** — the design reasoning, including what Wiggle deliberately makes explicit.

The [DSL cookbook](/docs/dsl-cookbook/) is the operator-by-operator companion: eight runnable
workflows exercising everything on these pages (`./gradlew :example:runCookbook`).
