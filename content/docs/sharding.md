# Sharding

One Wiggle cluster can spread its instances over several databases. Each instance lives entirely on
one database, its **shard**, so its transactions never span two. Every server node connects to every
shard, and clients never see shards. [Tutorial 3](/tutorial/sharded/) walks through a two-shard
setup end to end.

Sharding ships in the release after 0.0.9.

## Model

| Term | Meaning |
|---|---|
| **shard** | One primary database plus zero or more read replicas, with a permanent integer id that is never reused. |
| **`instances` role** | The shard takes workflow instances, minted onto it by weight. |
| **`home` role** | Exactly one shard. Holds the cluster-wide rows: the node table and leadership, schedules, event cursors and the shard registry. |
| **`auth` role** | Exactly one shard. Holds portal accounts, roles, sessions and API credentials. The home shard takes it when no shard claims it. |
| **`search` role** | Zero or more shards that hold the search index and vectors, built off the hot path. |
| **generation** | One version of placement: from `activeFrom`, new root instances go to shards in proportion to `weights`. |

## The topology document

`WIGGLE_STORAGE_TOPOLOGY` names a JSON document: a file path, or the document itself when the value
starts with `{`. It replaces `WIGGLE_JDBC_URL`; setting both is refused.

```json
{
  "defaults": {
    "user": "${WIGGLE_JDBC_USER}",
    "password": "${WIGGLE_JDBC_PASSWORD}",
    "pool": 32,
    "replicaPool": 16,
    "maxReplicaLagMillis": 5000,
    "replicaFallback": "primary"
  },
  "generations": [
    { "id": 1, "activeFrom": "2026-10-01T00:00:00Z", "weights": { "0": 1, "1": 1 } },
    { "id": 2, "activeFrom": "2026-11-02T09:00:00Z", "weights": { "0": 1, "1": 1, "2": 3 } }
  ],
  "shards": [
    { "id": 0, "state": "active", "roles": ["instances", "home"],
      "primary":  { "url": "jdbc:postgresql://pg-s0:5432/wiggle" },
      "replicas": [ { "url": "jdbc:postgresql://pg-s0-r1:5432/wiggle" } ] },
    { "id": 1, "state": "active", "roles": ["instances"],
      "password": "${WIGGLE_S1_PASSWORD}",
      "primary":  { "url": "jdbc:postgresql://pg-s1:5432/wiggle" } },
    { "id": 2, "state": "active", "roles": ["instances"],
      "primary":  { "url": "jdbc:postgresql://pg-s2:5432/wiggle" } },
    { "id": 10, "state": "active", "roles": ["auth"],
      "primary":  { "url": "jdbc:postgresql://pg-auth:5432/wiggle" } },
    { "id": 20, "state": "active", "roles": ["search"],
      "primary":  { "url": "jdbc:postgresql://pg-search:5432/wiggle" } }
  ]
}
```

- **Settings cascade.** `user`, `password`, `pool`, `replicaPool`, `maxReplicaLagMillis` and
  `replicaFallback` can be set in `defaults`, overridden per shard, and overridden again per
  primary or replica.
- **`${NAME}`** is replaced from the environment, and nothing else is interpolated. An unset
  variable stops the node from starting, so the document can be a ConfigMap while credentials stay
  in Secrets.
- **Names are case-insensitive**: `active` and `ACTIVE`, `home` and `HOME` are the same.

A node refuses to start, naming the problem, when the document:

- lists a shard id twice, or has other than exactly one `home` and one `auth` shard;
- weights a shard that is not `active` or has no `instances` role, or has no positive weight at all;
- has generations whose `id` or `activeFrom` do not both increase;
- leaves out a shard the registry still lists as not retired;
- points a shard at a database already claimed by another shard id.

On start, each node migrates every shard and logs the connections it opens per shard: `pool` plus
one `replicaPool` per replica. Size each database's `max_connections` from that times the node count.

## Ids

An instance id names its shard: `wfi.s3.01k6…` lives on shard 3. Its tokens (`tok.s3.…`) and its
sub-workflows carry the same shard, so a report, a heartbeat or a child instance routes by its id
alone, with no lookup. The shard is fixed at mint time and never recomputed from the topology.

Ids from before sharding (`wfi_…`, `tok_…`) and ids minted under the removed coordinator route to
the home shard. That is why upgrading a single-database deployment rewrites no rows.

## What goes where

| Operation | Where it runs |
|---|---|
| start, report, fail, heartbeat, signal, cancel | the instance's shard, by its id |
| claim (a worker's poll) | one shard at a time from a rotating start, returning the first that has work |
| timers, retries, signal deadlines, lease reclaim, retention | the leader sweeps every shard in parallel |
| registering a workflow | every shard, so each instance reads its graph from its own database |
| schedules, the node table, leadership, event cursors | the home shard |
| event log feed | every shard, merged |
| portal lists, search, counts | every shard in parallel, from replicas where allowed, merged by `(created_at, id)` |
| the view after an action (cancel, retry, signal) | the primary of the instance's shard |
| sign-in, sessions, users and roles | the auth shard |
| full-text and vector search | every search shard, merged |

Within a shard, claims serve the oldest instance first. Across shards there is no global order.
There is one leader for the whole cluster, elected on the home shard.

## Read replicas

Each shard can list `replicas`. Read-heavy portal queries (lists, search, counts) go to a replica
whose lag is within `maxReplicaLagMillis`; anything that must see a write goes to the primary. With
no healthy replica, `replicaFallback` decides: `primary` serves the read from the primary, `fail`
refuses it, which protects the primary from search load while replicas are down.

Lag is measured from a heartbeat the leader writes to every primary once a second, so it works on
an idle database. It counts clock skew between nodes, so keep `maxReplicaLagMillis` well above it.

A single-database deployment gets replicas without a topology document:

| Variable | Default | Meaning |
|---|---|---|
| `WIGGLE_JDBC_REPLICA_URLS` | (unset) | comma-separated replica URLs |
| `WIGGLE_JDBC_REPLICA_POOL_SIZE` | `16` | pool per replica |
| `WIGGLE_JDBC_MAX_REPLICA_LAG_MILLIS` | `5000` | a replica further behind serves no reads |
| `WIGGLE_JDBC_REPLICA_FALLBACK` | `primary` | `primary` or `fail` |

## Adding a shard

No existing row ever moves.

1. Provision the database. Add it to `shards` as `active` with no weight, and roll the document out
   to every node. Nodes migrate it and can route to it; nothing is minted there.
2. Register your workflows again. Registration is idempotent and writes to every shard, so the new
   shard holds every definition before it takes work.
3. Append a generation that weights it, with `activeFrom` after the rollout completes, and roll that
   out. Each node keeps minting under the previous generation until `activeFrom`.

Instances stay on the shard they were minted on until they finish, so load evens out within about
one instance lifetime. A new, empty shard can take a higher weight to catch up sooner. A node asked
to route to a shard its topology does not know yet answers `UNAVAILABLE` (retryable), not
*not found*.

## Draining and retiring

1. Append a generation without the shard, and set its state to `draining`. It mints nothing and
   keeps serving every instance it holds.
2. Wait until it holds no running instance and retention has purged the finished ones.
3. Set it to `retired`. Routes to it now answer *not found*.
4. Decommission the database. Its id is never reused.

A shard cannot retire while it holds a running instance or an event a consumer has not
acknowledged. The home and auth shards are never drained.

## Auth and search shards

**Auth.** Portal accounts, roles, sessions and API credentials live on the auth shard. Each node
caches them (`WIGGLE_AUTH_CACHE_MILLIS`) and drops a cached entry within a second of a change.

**Search.** Full-text and vector search read a search index kept on `search` shards, never on the
instance shards: indexing a vector costs far more than a B-tree insert, and the instance shards are
what reach the ceiling. The leader feeds the index from the event log, off the hot path, so a search
can lag the instances it covers by a few seconds.

## Upgrading

- **From one database.** Its database becomes the home shard. Write a topology with that one shard
  (`instances` and `home`), switch `WIGGLE_JDBC_URL` for `WIGGLE_STORAGE_TOPOLOGY`, then add shards as
  above. Existing ids route home, and no row is rewritten.
- **From the cell coordinator.** The coordinator, cells, namespaces and epochs are removed. Drain
  every cell but one; that cell's database becomes the home shard. `WIGGLE_COORDINATOR_URL`,
  `WIGGLE_NAMESPACE`, `WIGGLE_CELL_ID` and the other coordinator settings now stop a node from
  starting, with a message naming what replaces them. For per-tenant isolation, run a separate
  cluster per tenant.
