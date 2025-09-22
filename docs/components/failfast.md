# Fail Fast

## Overview

Fail Fast immediately fails operations when a system is in a known failure state, rather than allowing futile retries or wasted resources. This pattern is useful for protecting systems from cascading failures and reducing recovery time.

## Use Cases

- Prevent resource exhaustion when a dependency is known to be down
- Reduce latency by failing quickly instead of waiting for timeouts
- Allow rapid recovery by blocking requests until the system is healthy

## Usage

=== "decorator"

```python
{!> ../../snippets/failfast/failfast_decorator.py !}
```

=== "context manager"

```python
{!> ../../snippets/failfast/failfast_context.py !}
```

::: failsafe.failfast.failfast
    :docstring:

## Recovery

Fail Fast should be paired with health checks or circuit breakers to automatically recover when the dependency is healthy again.
