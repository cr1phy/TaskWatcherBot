from aiogram import Router
from .owner import router as owner_router
from .user import router as user_router

router = Router()
router.include_router(user_router)
router.include_router(owner_router)
