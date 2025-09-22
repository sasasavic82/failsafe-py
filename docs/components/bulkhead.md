# Bulkheads

## Overview

A bulkhead isolates resources by capping how many executions of a specific operation can run at once. Use separate bulkheads per feature so one path cannot starve others. In effect, it is per-operation concurrency control and a form of [rate limiting](rate_limiter.md).

## Implementations

* Multithreaded: fixed-size worker pool with a queue.
* Event loop (Failsafe): semaphore-based concurrency limiting.

## Use Cases

* Cap concurrent requests for a subsystem so load spikes do not drain shared resources.
* Shed excess load predictably instead of degrading the entire service.

## Usage

=== "decorator"

```Python hl_lines="1 7"
{!> ./snippets/bulkhead/bulkhead_decorator.py !}
```

=== "context manager"

```Python hl_lines="1 4 12"
{!> ./snippets/bulkhead/bulkhead_context.py !}
```

\::: failsafe.bulkhead.bulkhead
\:docstring:

## Adaptive Limiting

Concurrency can be adjusted dynamically using latency statistics against a target objective.

