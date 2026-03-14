import asyncio
import sys

from .bootstrap import main

if sys.platform == "win32":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
asyncio.run(main())
