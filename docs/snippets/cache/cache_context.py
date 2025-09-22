import asyncio
from failsafe.cache import cache

cache_instance = cache(maxsize=128)

async def get_user_profile(user_id: str) -> dict:
    async with cache_instance:
        ...

asyncio.run(get_user_profile(user_id="1234"))
