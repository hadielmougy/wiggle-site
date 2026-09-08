# Per-tenant isolation with cells

<div class="chips"><span>cells</span><span>epochs</span><span>coordinator</span><span>zero-migration resharding</span></div>

## The problem

Tenant A's Black Friday cannot be allowed to take down tenant B's checkout. Logical namespaces in
a shared database don't deliver that — the noisy neighbor shares your buffer pool, your WAL, your
connection limit, your blast radius. And when you *do* split tenants up, the day one tenant
outgrows its slice you're staring at a data migration.

## The shape

A **namespace** maps to one or more **cells**; each cell is a complete deployment — its own
server cluster *and its own database*. A small Raft-backed coordinator owns placement:

```bash
# every role is the same image
WIGGLE_ROLE=coordinator WIGGLE_COORD_STORE=ratis:///var/lib/wiggle/coord   # control plane
WIGGLE_ROLE=cell WIGGLE_CELL_ID=cellA WIGGLE_NAMESPACE=orders \
  WIGGLE_COORDINATOR_URL=coordinator:8099 WIGGLE_JDBC_URL=jdbc:postgresql://dbA/wiggle
```

```bash
# publish the shard→cell ring: instances spread over cells by consistent hashing
wiggle use coordinator prod:8099
wiggle open-epoch -n orders 0=cellA 1=cellB
```

Clients and workers don't change — they resolve through the coordinator:

```java
try (var wiggle = WiggleConnection.coordinator("coordinator:8099", tls, "eu-west")) {
    wiggle.clientForNamespace("orders").start(orders, order);   // routed to the owning cell
}
```

A `NamespaceWorker` fans one worker out across the namespace's live cells and follows rebalances
automatically.

## Why this shape

- **Isolation is physical, not logical.** A cell's database melting down affects that cell. Other
  tenants are on other databases — different failure domains, different capacity, possibly
  different hardware.
- **Resharding never migrates data.** Publishing a new shard→cell ring is an **epoch bump**: new
  instances follow the new ring; in-flight instances finish where they live and drain naturally.
  Adding a cell under load is a control-plane operation, not a data operation.
- **Routing is directory-free.** The instance id embeds namespace, epoch, and shard
  (`orders.e0.s3.01J…`) — any party computes the owning cell from the id alone. No lookup table
  to cache, no directory service on the request path.
- **The control plane is self-contained.** The coordinator is a Raft group over embedded
  Ratis + RocksDB — no external database, no etcd. Kill it under load and running work doesn't
  notice; new-start routing recovers in seconds with state intact
  ([measured](/performance/)).

## Variations

- **Cells without multi-tenancy**: the same mechanics scale a single huge namespace past one
  database's ceiling — shard 0..n over cells by throughput, not by tenant.
- **Drain and retire**: to decommission a cell, open a new epoch without it; the coordinator
  retires the old epoch automatically once its instances finish.
- Start without any of this — the coordinator is opt-in, and a single cluster runs unchanged.
  The [sharding & epochs doc](/docs/sharding-and-epochs/) covers the model in depth.
