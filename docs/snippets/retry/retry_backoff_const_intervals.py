import asyncio

import httpx

from failsafe.retry import retry


@retry(on=httpx.NetworkError, attempts=4, backoff=(0.5, 1.0, 1.5, 2.0))
async def get_user_data(user_id: str) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://682eb4bc746f8ca4a47dfdc9.mockapi.io/api/v1/users/{user_id}")

        return response.json()


asyncio.run(get_user_data("1"))
