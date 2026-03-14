from aiogram import Router

from .linking import router as linking_router
from .owner import router as owner_router
from .stats import router as stats_router

router = Router()
router.include_router(owner_router)
router.include_router(linking_router)
router.include_router(stats_router)
