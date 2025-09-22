import asyncio
from failsafe.featuretoggle import featuretoggle

@featuretoggle(enabled=True)
async def new_checkout_flow(user_id: str) -> None:
    """
    Run the new checkout flow if the feature is enabled
    """
    ...

asyncio.run(new_checkout_flow(user_id="1234"))
