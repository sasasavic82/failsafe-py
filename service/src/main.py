# main.py
import asyncio
from fastapi import FastAPI, HTTPException

from .telemetry import setup_otel

from failsafe.retry import retry
from failsafe.failfast import failfast, FailFastOpen
from failsafe.featuretoggle import featuretoggle, FeatureDisabled
from failsafe.hedge import hedge, HedgeTimeout
from failsafe.timeout import timeout, MaxDurationExceeded
from failsafe.bulkhead import bulkhead, BulkheadFull 
from failsafe.circuitbreaker import consecutive_breaker 
from failsafe.fallback import fallback

setup_otel("order-api")
app = FastAPI()


@hedge(name="price_quote", attempts=3, delay=0.03, timeout=0.25)
@retry(name="price_quote", attempts=3, backoff=0.5)
async def fetch_price(venue: str) -> float:
    await asyncio.sleep(0.1)
    return 123.45


@featuretoggle(name="beta_orders", enabled=True)
@failfast(name="orders_write_guard", failure_threshold=1)
async def create_order_impl(payload: dict) -> dict:

    # breaker: protect DB or remote dependency (emits breaker transitions)
    async with consecutive_breaker(name="db_breaker", failure_threshold=5, recovery_threshold=2):

        # timeout: bound critical section (emits timeout metrics)
        async with timeout(name="db_write_timeout", seconds=0.3):

            # pretend write to DB
            await asyncio.sleep(0.05)

    # TODO: add Cache/bulkhead/fallback
    price = await fetch_price(payload["venue"])
    return {"ok": True, "price": price}


@app.post("/orders")
async def create_order(payload: dict):
    try:
        result = await create_order_impl(payload)
        return result
    except FeatureDisabled:
        raise HTTPException(status_code=403, detail="feature disabled")
    except FailFastOpen:
        raise HTTPException(status_code=503, detail="fail-fast open")
    except HedgeTimeout:
        raise HTTPException(status_code=504, detail="pricing timed out")
    except MaxDurationExceeded:
        raise HTTPException(status_code=504, detail="db timeout")
