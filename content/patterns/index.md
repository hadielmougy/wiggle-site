# Patterns

Working shapes for real processes — each pattern is a **topology + handlers you can copy**, with
the reasoning for why the shape looks the way it does. All of them run against an embedded server
in one JVM, so every pattern is testable before it's deployed.

<div class="grid">
<a class="cardlink" href="/patterns/fork-join/"><span class="card"><span class="ct">⑂ Parallel fork / join</span><span class="cd">Run independent branches concurrently on isolated state; rejoin through an explicit, hand-written combine. The foundation everything else builds on.</span></span></a>
<a class="cardlink" href="/patterns/approval/"><span class="card"><span class="ct">✋ Human-in-the-loop approval</span><span class="cd">Park the instance on a signal — no worker held — with a deadline that escalates when nobody acts, and a branch on which of the two happened.</span></span></a>
<a class="cardlink" href="/patterns/fan-out/"><span class="card"><span class="ct">⇶ Dynamic fan-out</span><span class="cd">One isolated branch per element of a runtime collection; results collected in input shape and folded by an explicit combine.</span></span></a>
<a class="cardlink" href="/patterns/retries/"><span class="card"><span class="ct">↻ Retries &amp; failure isolation</span><span class="cd">Exponential backoff per step, gates for business-level "stop cleanly", and poll-until-ready loops for external dependencies.</span></span></a>
<a class="cardlink" href="/patterns/scheduled/"><span class="card"><span class="ct">⏰ Cron &amp; scheduled work</span><span class="cd">Server-side cron and interval schedules with exactly-once firing across leader failover — no external scheduler.</span></span></a>
<a class="cardlink" href="/patterns/microservices/"><span class="card"><span class="ct">🧵 One flow, many services</span><span class="cd">Route each step to a queue; separate services (in separate languages) each serve only their steps of the same durable instance.</span></span></a>
<a class="cardlink" href="/patterns/cells/"><span class="card"><span class="ct">🧫 Per-tenant isolation</span><span class="cd">Give a tenant its own cell — database and cluster — behind one coordinator, with zero-migration resharding when load grows.</span></span></a>
</div>

## How to read a pattern

Every page follows the same skeleton:

1. **The problem** — when you reach for this shape.
2. **The topology** — the graph, in the DSL.
3. **The handlers** — plain methods matched by name; the signature picks the step kind.
4. **Why this shape** — the design reasoning, including what Wiggle deliberately makes explicit.

The [DSL cookbook](/docs/dsl-cookbook/) is the operator-by-operator companion: eight runnable
workflows exercising everything on these pages (`./gradlew :example:runCookbook`).
