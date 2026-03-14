from aiogram import Router

from ..middleware import PrivateOnlyMiddleware
from .linking import router as linking_router
from .owner import router as owner_router
from .stats import router as stats_router

router = Router()
router.message.outer_middleware(PrivateOnlyMiddleware())
router.callback_query.outer_middleware(PrivateOnlyMiddleware())
router.include_router(linking_router)
router.include_router(stats_router)
router.include_router(owner_router)  # last — OwnerMiddleware must not block others
