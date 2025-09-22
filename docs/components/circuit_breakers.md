# Circuit Breakers

## Overview

When a downstream service is degraded, blind [retries](./retry.md) amplify load, waste latency budgets, and stall upstreams. Circuit breakers cut off failing paths early once error signals cross a threshold.

A breaker tracks failures over time. When they exceed configured limits, it **blocks calls for a cooldown window**, giving the dependency space to recover and protecting the rest of the system.

## When to Use

* **Subsystem isolation and observability**: segment dependencies; emit metrics per segment to localize faults quickly.
* **Fail fast on persistent errors**: reduce tail latencies by avoiding doomed waits.
* **Load shedding**: stop piling requests onto a broken dependency.

## State Model

Circuit breakers are state machines:

* `Working` *(closed)* - dependency healthy; calls pass.
* `Failing` *(open)* - dependency unhealthy; calls short-circuit.
* `Recovering` *(half-open)* - cooldown elapsed; probe with limited calls.

!!! note
Failsafe uses descriptive state names rather than the electrical metaphor to reduce ambiguity.

## Usage

Two forms:

=== "decorator"

```python hl_lines="6 15-19 22"
{!> ./snippets/circuit_breakers/breaker_decorator.py !}
```

=== "context manager"

```python hl_lines="6 15-19 23"
{!> ./snippets/circuit_breakers/breaker_context.py !}
```

!!! note
Breakers are stateful. Instantiate once per dependency and inject wherever that dependency is consumed.

!!! warning
Assumes AsyncIO best practices: keep CPU-bound work off the event loop. Otherwise cooldown timers may fire late.

## Breaker Types

### Consecutive Breaker

\::: failsafe.circuitbreaker.consecutive\_breaker
\:docstring:
