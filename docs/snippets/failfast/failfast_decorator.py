import asyncio
from failsafe.failfast import failfast

@failfast(failure_threshold=3)
async def process_payment(order_id: str) -> None:
    """
    Process a payment, but fail fast if too many failures occur
    """
    ...

asyncio.run(process_payment(order_id="A123"))
