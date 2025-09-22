# failsafe.bulkhead

Bulkhead limits how many times a given action can run at once so it cannot monopolize the asyncio event loop. It enforces hard caps on executions-especially concurrent in-flight executions-for that code path.

When calls exceed the configured limit, the bulkhead is full and new attempts are rejected with an exception. This prevents a caller from overwhelming the application by repeatedly triggering the action.

Viewed differently: a bulkhead is a throttle and isolation barrier for a specific operation.

## Reference

- (Bulkhead)[https://www.geeksforgeeks.org/system-design/bulkhead-pattern/]