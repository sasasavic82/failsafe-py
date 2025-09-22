import asyncio

import httpx

from failsafe.retry import retry
from failsafe.retry.backoffs import fibo


@retry(on=httpx.NetworkError, backoff=fibo(min_delay_secs=10, factor_secs=5))
async def get_user_data(user_id: str) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://682eb4bc746f8ca4a47dfdc9.mockapi.io/api/v1/users/{user_id}")

        return response.json()


asyncio.run(get_user_data("3"))
