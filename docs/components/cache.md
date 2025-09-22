# Cache

## Overview

Caching stores the results of expensive or frequently repeated operations, reducing latency and load on downstream systems. It is a fundamental technique for improving performance and reliability in distributed systems.

## Use Cases

- Avoid recomputing expensive results (e.g., database queries, API calls)
- Reduce load on slow or rate-limited dependencies
- Improve perceived performance for end users

## Usage

=== "decorator"

```python
{!> ../../snippets/cache/cache_decorator.py !}
```

=== "context manager"

```python
{!> ../../snippets/cache/cache_context.py !}
```

::: failsafe.cache.cache
    :docstring:

## Eviction Policies

Caches have limited size. When full, old entries are evicted. Failsafe supports LRU (Least Recently Used) eviction by default.

!!! note
    Choose cache size and eviction policy based on workload and memory constraints.
