# Community & contributing

Wiggle is Apache-2.0 licensed and developed in the open. Contributions — issues, docs, patterns,
storage backends, client features — are welcome.

## Where things live

| | |
|---|---|
| **Engine, server, Java client** | [github.com/hadielmougy/wiggle](https://github.com/hadielmougy/wiggle) |
| **Go client** | [github.com/hadielmougy/wiggle-go](https://github.com/hadielmougy/wiggle-go) |
| **Python client** | [github.com/hadielmougy/wiggle-python](https://github.com/hadielmougy/wiggle-python) |
| **Maven Central** | [`io.github.hadielmougy`](https://central.sonatype.com/artifact/io.github.hadielmougy/wiggle-client) |
| **Issues & roadmap** | [GitHub issues](https://github.com/hadielmougy/wiggle/issues) |

## Good first contributions

The roadmap keeps an honest list — highlights that make good entry points:

- **Console topology view** — namespaces → cells → epochs/ring/roster, live placement.
- **Pending-signals over gRPC** — enumerate parked signal waits from the console in coordinator
  mode.
- **Compensation helpers** — first-class saga/compensation patterns.
- **Buffered signals** — deliver-before-wait semantics as an option.
- **A pattern you use** — the [patterns library](/patterns/) grows by real-world shapes; a PR with
  a topology + handlers + a paragraph of context is a great contribution.

## Building from source

JDK 21+, wrapper included:

```bash
git clone https://github.com/hadielmougy/wiggle && cd wiggle
./gradlew build          # full build + tests
./gradlew :example:run   # see it work
```

The engine is small enough to read in an afternoon — `server/` is the state machine,
`client/` the DSL and worker, `coordinator/` the cellular control plane.

## Ground rules

Be kind, be concrete, and bring a failing test when you can. Design discussions happen in issues;
significant changes should start with one so the approach is agreed before the diff exists.
