# Cron & scheduled work

<div class="chips"><span>createCronSchedule</span><span>createSchedule</span><span>leader failover</span></div>

## The problem

The nightly report must run at 03:00 — once. Not zero times because the box that had the crontab
was being rotated, and not twice because two replicas both thought they were the scheduler.

## The shape

Schedules are server-side objects that start a fresh instance of a registered workflow on a cron
expression or a fixed interval:

```java
Blueprint report = Workflow.define("nightly-report")
        .step("gather")
        .step("render")
        .effect("distribute")
        .build();
client.register(report);

// cron: 03:00 every day (server clock), optional payload for the started instances
client.createCronSchedule("nightly-report", "0 3 * * *", Map.of("scope", "all-tenants"));

// or a fixed interval
client.createSchedule("cache-refresh", Duration.ofMinutes(15), null);
```

Each firing starts a normal, fully durable instance — visible on the console, cancellable,
retried per its own policies, traced like anything else.

## Why this shape

- **Exactly-once firing across failover.** In a cluster, one node is elected leader for
  clock-driven duties (timers, schedules, lease recovery). When the leader dies, the new leader
  resumes the schedule — a firing happens once even across the transition, because due-times are
  claimed transactionally in the database, not tracked in process memory.
- **The schedule is data.** It survives restarts and deploys; there's no crontab to configure per
  host, no "which replica runs the cron?" question, no sidecar scheduler.
- **Fired work is workflow work.** The nightly report gets durability, retries, fan-out,
  signals — the whole vocabulary — instead of being a bare cron shell script that fails silently
  at 3 a.m.
- **Schedules are operable.** The console lists them, shows the last/next firing, and lets an
  operator create or delete them without a deploy.

## Variations

- A scheduled instance can immediately `forEach` over tenants — the 03:00 firing fans out into
  per-tenant isolated branches ([dynamic fan-out](/patterns/fan-out/)).
- Combine with [sub-workflows](/docs/dsl-cookbook/) to keep the scheduled parent thin: it just
  composes children that also run standalone.
- For "run this once, later" (not recurring), a `sleep` step at the head of a workflow is often
  simpler than a schedule.
