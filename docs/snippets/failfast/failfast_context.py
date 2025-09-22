import asyncio
from failsafe.failfast import failfast

failfast_instance = failfast(failure_threshold=3)

async def process_payment(order_id: str) -> None:
    async with failfast_instance:
        ...

asyncio.run(process_payment(order_id="A123"))
