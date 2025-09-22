# Feature Toggle

## Overview

Feature toggles (feature flags) allow you to enable or disable features at runtime without redeploying code. This pattern is essential for safe deployments, A/B testing, and gradual rollouts.

## Use Cases

- Enable/disable features for specific users or environments
- Roll out new functionality gradually
- Instantly disable problematic features in production

## Usage

=== "decorator"

```python
{!> ../../snippets/featuretoggle/featuretoggle_decorator.py !}
```

=== "context manager"

```python
{!> ../../snippets/featuretoggle/featuretoggle_context.py !}
```

::: failsafe.featuretoggle.featuretoggle
    :docstring:

## Best Practices

Feature toggles should be managed centrally and cleaned up after rollout to avoid technical debt.
