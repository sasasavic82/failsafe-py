# Rate Limiters

## Overview

Rate limiting caps the **request rate** to a level your service can sustain.

Applied at:

* **Server side** - protect your service.
* **Client side** - respect upstream limits.

Taxonomy:

* By **rate**: [Static](#static-rate-limiters), [Dynamic](#dynamic-rate-limiters)
* By **state**: [Local/In-Memory](#localin-memory-rate-limiters), [Distributed](#distributed-rate-limiters)

## Use Cases

* Throttle public API traffic at the gateway to resist DoS.
* Constrain calls to external or legacy systems on the client.
* Prevent “friendly-fire” overload across internal services.
* Enforce fair use per tenant/user.

## By Rate

### Static Rate Limiters

Configure an explicit rate (e.g., 100 req/s). The limiter counts and enforces that ceiling. Choose the value from load tests.

#### Token Bucket Rate Limiter

Bucket holds tokens. A request consumes one token; if empty, the request is rejected. Tokens refill at a constant rate of `1 / target_rate`.

=== "decorator"

```Python hl_lines="1 6"
{!> ./snippets/ratelimiter/ratelimiter_decorator.py !}
```

=== "context manager"

```Python hl_lines="1 4 12"
{!> ./snippets/ratelimiter/ratelimiter_context.py !}
```

\::: failsafe.ratelimit.tokenbucket
\:docstring:

### Dynamic Rate Limiters

Static rates drift as code and infrastructure change. Instead of guessing a rate, drive toward full resource utilization by controlling **concurrency** and shedding excess load. Use Adaptive Request Concurrency (dynamic [bulkhead](./bulkhead.md#adaptive-limiting)).

## By State

### Local/In-Memory Rate Limiters

State lives in each process. Effective global capacity scales with instance count:

* 1 instance → 10 req/s
* 2 instances → 20 req/s
* 10 instances → 100 req/s

Simple, dependency-free, and protects each instance. Loses state across restarts. If you need a hard global SLA, use distributed state.

!!! note
Failsafe currently supports only local/in-memory state.

### Distributed Rate Limiters

State stored externally (e.g., Redis, Memcached). Global limits hold regardless of instance count or deploys. Requires an external store; use when a strict SLA is mandatory.

!!! note
Distributed components are not supported in Failsafe at this time.

## Best Practices

### Shard Rate Limits

Apply limits per shard, not globally. Common shards:

* `user_id` (per-user fairness)
* Route/endpoint (prioritize critical paths)
* Read vs write, or by cost class

This is a form of [bulkheading](./bulkhead.md).

### Rate Limit Public API

Public endpoints fan out to internal systems and attract the heaviest load. Gate them with rate limits. If no contractual SLA exists, local limits are sufficient. If an SLA exists, use distributed limits.
