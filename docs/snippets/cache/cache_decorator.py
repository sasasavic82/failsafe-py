import asyncio
from failsafe.cache import cache

@cache(maxsize=128)
async def get_user_profile(user_id: str) -> dict:
    """
    Fetch user profile from a remote service or database
    """
    ...

asyncio.run(get_user_profile(user_id="1234"))
