import asyncio
from failsafe.hedge import hedge

hedge_instance = hedge(timeout=0.2)

async def fetch_data() -> dict:
    async with hedge_instance:
        ...

asyncio.run(fetch_data())
