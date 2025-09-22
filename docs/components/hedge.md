# Hedge

## Overview

Hedging reduces tail latency by running backup (hedged) requests in parallel if the primary is slow. This technique is used by large-scale distributed systems to improve reliability and user experience.

## Use Cases

- Reduce impact of unpredictable or slow dependencies
- Improve latency for critical user-facing operations
- Mask transient network or infrastructure hiccups

## Usage

=== "decorator"

```python
{!> ../../snippets/hedge/hedge_decorator.py !}
```

=== "context manager"

```python
{!> ../../snippets/hedge/hedge_context.py !}
```

::: failsafe.hedge.hedge
    :docstring:

## Tuning

Set the hedging timeout based on your latency SLOs and the cost of duplicate work. Too aggressive hedging can increase backend load.

!!! warning
    Hedging is most effective for idempotent operations.
