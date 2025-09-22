import asyncio
from failsafe.hedge import hedge

@hedge(timeout=0.2)
async def fetch_data() -> dict:
    """
    Fetch data from a slow or unreliable service
    """
    ...

asyncio.run(fetch_data())
