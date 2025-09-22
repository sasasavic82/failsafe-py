# Roadmap

This page provides some transparency on Failsafe roadmap and future plans. 

!!! note
    Failsafe is an internal Telstra project and is not open for outside contributions.

## M0: The Internal Release

**Status**: Ongoing

### Goals

* Provide the baseline implementation for all general reliability components
* Init documentation. Document the components
* Implement project's infrastructure

## M1: Observability

**Status**: Ongoing

Implement metrics to support white-box monitoring of the components

### Github Milestones

* Observability

### Goals

* Design an event system to hook into the component's lifecycle
* Provide a standalone library to integrate with [OpenTelemetry](https://opentelemetry.io/) metrics
* Provide a standalone library to integrate with [Prometheus](https://prometheus.io/) metrics

## M2: API Framework Integration

**Status**: Ongoing

Integrate with some popular frameworks to provide easy low-code solutions to common problems.

### Goals

* Implement a standalone library to integrate with FastAPI
* Implement rate limiting middlewares
* Implement distributed timeouts 

## M3: Resiliency Workshop App

**Status**: Upcoming

Resiliency Workshop App is an example system that uses Failsafe to ensure resiliency and self-healing. 

### Goals

* Apply Failsafe components to Telstra's Resiliency Workshop App
* Test Failsafe components in composition

## M3: Advanced Breakers

**Status**: Future

### Goals

* Implement error-rate-based sliding window breaker
* Implement error-count-based sliding window breaker


## MX: Distributed components

**Status**: Future

Implement a distributed versions of the components based on Redis

### Goals

* Implement distributed rate limiting based on Redis
* Implement distributed circuit breakers based on Redis
