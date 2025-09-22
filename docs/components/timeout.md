# Timeouts

## Overview

Work takes time. Resources are finite. Set an upper bound-**a timeout**-so calls don’t occupy capacity indefinitely.

Many clients expose timeouts directly:

* [HTTPX: Timeouts](https://www.python-httpx.org/compatibility/#timeouts)
* [AIOHTTP: Timeouts](https://docs.aiohttp.org/en/stable/client_quickstart.html#timeouts)
* [gRPC: ClientCallDetails](https://grpc.github.io/grpc/python/grpc_asyncio.html#grpc.aio.ClientCallDetails)
* [IOTHRIFT: Client Timeout](https://aiothrift.readthedocs.io/en/latest/examples.html?highlight=timeout#aio-thrift-client)

Where no built-in exists, Failsafe provides a decorator and context manager.

## Use Cases

* Cap caller wait time for local work. Prefer **local timeouts** when no downstream calls are involved.
* Bound an end-to-end request chain with a **distributed timeout** (deadline/budget).

## By Locality

### Local Timeouts

=== "decorator"

```Python hl_lines="3 6"
{!> ./snippets/timeout/timeout_decorator.py !}
```

=== "context manager"

```Python hl_lines="3 10"
{!> ./snippets/timeout/timeout_context.py !}
```

::: failsafe.timeout.timeout
:docstring:

!!! warning
Assumes AsyncIO best practices. Keep CPU-bound work off the event loop or timers may fire late.

### Distributed Timeout

Single-process timeouts are insufficient in distributed systems. A request may sit in a queue; the caller times out and moves on, but the queued work still executes-wasting resources.

Solution: propagate a **deadline** along the call chain so each service knows the remaining time. If the budget is exhausted, drop or short-circuit the work.

!!! info
Failsafe does not yet ship a turnkey deadline propagation layer; this requires integration with your API framework. See the [roadmap](../roadmap.md).
