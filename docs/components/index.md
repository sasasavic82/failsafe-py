# Introduction

## From Monoliths to Distributed Systems

The last decade reshaped software delivery.

We used to deploy a single, cohesive application. As success and traffic grew, those systems needed rapid iteration and scale. Vertical scaling hit limits-hardware gains lagged demand, and high-end machines were costly.

Scale wasn’t the only pressure. Availability expectations rose. A multi-hour 503 “maintenance” page became unacceptable. Users expect systems to be continuously available.

Teams scaled too. What once fit in the heads of a few dozen engineers now spans many teams and thousands of people. No one person can fully reason about the whole.

Industry leaders (Google, AWS, Netflix, Meta) converged on a different architecture: **split the monolith into small, independently deployable services**-**microservices**-that run on commodity hardware and scale horizontally (budget permitting).

## The Microservice Era

Decomposing monoliths is harder than it sounds. Microservices multiply moving parts, with components spread across machines and networks.

You now watch the health of **N** nodes, not one. Hardware fails. Networks are unreliable: packets drop, cables break, routers die. Latency, bandwidth, and topology matter.

The result is a system that must **assume failure**. Failure is not an edge case; it is the baseline. Design for failure.

## About Failures and Limits

Distributed systems trade fewer total outages for more **partial failures**: specific subsystems degrade (errors, latency, timeouts) while others remain functional.

This is the common case. Design around it: what happens if any dependency is slow, erroring, or silent?

An unconstrained system fails in unpredictable ways and responds slowly under stress. Reliability engineering imposes **limits** so systems **fail in known, bounded ways**. See: [Take It to the Limit-Considerations for Building Reliable Systems](https://bravenewgeek.com/take-it-to-the-limit-considerations-for-building-reliable-systems/).

## Reliability Engineering

**Failsafe** is a production-oriented **resiliency toolkit**. It provides proven primitives that constrain failure modes and reduce blast radius.

Two classes of components:

* **Reactive** - do not prevent faults; contain and ride through them.
* **Proactive** - impose bounds so the system fails predictably.

## Components


Current Failsafe components:

#### Reactive

* [Retries](retry.md)
* [Cache](cache.md)
* [Hedge](hedge.md)
* [Circuit Breakers](circuit_breakers.md)
* [Timeouts](timeout.md)
* [Fallbacks](fallback.md)

#### Proactive

* [Bulkheads](bulkhead.md)
* [Rate Limiters](rate_limiter.md)
* [Fail Fast](failfast.md)
* [Feature Toggle](featuretoggle.md)

## Alternatives

Failsafe is one approach. Others include:

* **Service Meshes** - In containerized environments, push resiliency to sidecars (often [Envoy](https://www.envoyproxy.io/)) and communicate through them. This decouples resilience from application code.
* **Asynchronous, Event-Driven Systems** - Highly available queues (e.g., [Apache Kafka](https://kafka.apache.org/)) add resilience via transport semantics and decoupling, enabling patterns like buffering, retries, and backpressure.
