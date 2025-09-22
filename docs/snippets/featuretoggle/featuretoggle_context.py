import asyncio
from failsafe.featuretoggle import featuretoggle

feature_toggle = featuretoggle(enabled=True)

async def new_checkout_flow(user_id: str) -> None:
    async with feature_toggle:
        ...

asyncio.run(new_checkout_flow(user_id="1234"))
