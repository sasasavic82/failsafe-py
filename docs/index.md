<p align="center">
  <img src="../docs/failsafe-logo.png" alt="Failsafe" style="max-width:350px;width:100%;height:auto;">
</p>
<p align="center">
    <em>Fault tolerance for resiliency and stability in modern Python applications</em>
</p>

---

**Failsafe** is a collection of battle-tested resiliency patterns for building <a href="https://en.wikipedia.org/wiki/Microservices">microservice-based</a> applications.

Failsafe is intended as a Python counterpart to <a href="https://github.com/failsafe-lib/failsafe">Failsafe (Java)</a>.

## Key Features

* Implements commonly used resiliency patterns with configurations informed by industry practice (AWS, Google, Netflix)
* Idiomatic Python via <a href="https://realpython.com/primer-on-python-decorators">decorators</a> and <a href="https://realpython.com/python-with-statement">async context managers</a>
* <a href="https://docs.python.org/3/library/asyncio.html">AsyncIO</a>-native
* Lightweight, readable, testable

## Requirements

* Python 3.12+

## Installation

Failsafe is currently available internally to Telstra.

```bash
uv sync
```

## Components

| Component                                           | Problem                                                                                    | Solution                                                                                          | Implemented |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- | ----------- |
| [Retry](./components/retry.md)                      | Transient failures that self-recover after a short time                                    | Automatically retry operations on temporary failures                                              | Yes         |
| [Cache](./components/cache.md)                      | Recomputing or refetching identical data is wasteful and slow                              | Store and reuse results of expensive operations                                                   | Yes         |
| [Hedge](./components/hedge.md)                      | Slow or unpredictable responses from a service increase tail latency                       | Run backup (hedged) requests in parallel to reduce latency and improve reliability                | Yes         |
| [Fail Fast](./components/failfast.md)               | When a system is in a known failure state, further attempts are futile and waste resources | Immediately fail operations when a failure threshold is reached, until recovery is detected       | Yes         |
| [Feature Toggle](./components/featuretoggle.md)     | Need to enable or disable features at runtime without code changes or redeployments        | Dynamically enable or disable code paths using feature flags                                      | Yes         |
| [Circuit Breaker](./components/circuit_breakers.md) | Overloaded or failing downstream services can worsen under additional load                 | Trip the breaker when failures exceed thresholds; probe for recovery before resuming full traffic | Yes         |
| [Timeout](./components/timeout.md)                  | Some operations may hang or take longer than acceptable                                    | Bound execution time with deterministic timeouts                                                  | Yes         |
| [Bulkhead](./components/bulkhead.md)                | Unbounded concurrency can exhaust resources and degrade the entire application             | Limit concurrent executions; queue or reject overflow                                             | Yes         |
| [Rate Limiter](./components/rate_limiter.md)        | Uncontrolled request rate can overload services                                            | Enforce a maximum request rate                                                                    | Yes         |
| [Fallback](./components/fallback.md)                | Dependencies can be down or degraded                                                       | Degrade gracefully with defaults or alternative code paths                                        | Yes         |

## License

Not for distribution
