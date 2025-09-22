import asyncio

import httpx

from failsafe.retry import retry


@retry(on=httpx.NetworkError, backoff=0.5)  # delay 500ms on each retry
async def get_user_data(user_id: str) -> None:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://682eb4bc746f8ca4a47dfdc9.mockapi.io/api/v1/users/{user_id}")

        return response.json()


asyncio.run(get_user_data("2"))
