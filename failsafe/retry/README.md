# failsafe.retry

Retry is the most basic component in the resiliency toolkit. 
It wraps some function that listen to exceptions it raises. 
If the specified exceptions are thrown, it retries in some time in a way that was specified.


## References

- [invl/retry](https://github.com/invl/retry)
- [litl/backoff](https://github.com/litl/backoff)