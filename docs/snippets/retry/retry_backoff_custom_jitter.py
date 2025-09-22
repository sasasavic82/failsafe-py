import asyncio
import random
from functools import partial

import httpx

from failsafe.retry import retry
from failsafe.retry.backoffs import expo


def randomixin(delay: float, *, max_mixing: float = 20) -> float:
    """
    Custom Random Mixin Jitter
    """

    return delay + random.uniform(0, max_mixing)


@retry(on=httpx.NetworkError, backoff=expo(min_delay_secs=20, jitter=partial(randomixin, max_mixing=50)))
async def get_user_data(user_id: str) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://682eb4bc746f8ca4a47dfdc9.mockapi.io/api/v1/users/{user_id}")

        return response.json()


asyncio.run(get_user_data("2"))
