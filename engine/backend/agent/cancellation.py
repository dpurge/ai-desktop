import asyncio
from collections.abc import Awaitable
from typing import Any

CANCELLED: Any = object()


async def run_unless_cancelled(awaitable: Awaitable, cancel_event: asyncio.Event) -> Any:
    """Await the result, or stop it and return CANCELLED as soon as the event is set."""
    work = asyncio.ensure_future(awaitable)
    cancel_wait = asyncio.ensure_future(cancel_event.wait())
    try:
        await asyncio.wait({work, cancel_wait}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        cancel_wait.cancel()
        if not work.done():
            # Cancelling lets the work clean up (for example, kill its process) before we go on.
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
    return CANCELLED if work.cancelled() else work.result()
