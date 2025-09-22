# Fallbacks

## Overview

When retries are exhausted or circuit breakers open, avoid cascading failures by executing a predefined Plan B. A fallback supplies a safe response or alternate path so upstreams keep moving.

## Use Cases

* Return a default or cached value when a dependency is unresponsive (e.g., placeholder avatar).
* Swallow and record noncritical failures (e.g., broker outage where message loss is acceptable).
* Switch to a redundant provider or pathway (e.g., secondary FX-rate API).

## Usage

```python hl_lines="4 8 15"
{!> ./snippets/fallback/fallback_decorator.py !}
```
