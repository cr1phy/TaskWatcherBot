from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.db.user import User
from app.services.groups import GroupRegistry
from app.services.user import UserService


class TestUserService:
    def _make_service(self, record=None, records=None, exists=False):
        dao = MagicMock()
        dao.get_by_tg_id = AsyncMock(return_value=record)
        dao.get_all = AsyncMock(return_value=records or [])
        dao.exists = AsyncMock(return_value=exists)
        dao.create = AsyncMock()

        service = UserService.__new__(UserService)
        service._dao = dao
        return service

    @pytest.mark.asyncio
    async def test_get_returns_user(self) -> None:
        record = {"tg_id": 1, "student_id": 10, "group_number": 5}
        service = self._make_service(record=record)
        user = await service.get(1)
        assert isinstance(user, User)
        assert user.tg_id == 1
        assert user.student_id == 10
        assert user.group_number == 5

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self) -> None:
        service = self._make_service(record=None)
        user = await service.get(999)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_all_returns_list_of_users(self) -> None:
        records = [
            {"tg_id": 1, "student_id": 10, "group_number": 5},
            {"tg_id": 2, "student_id": 11, "group_number": 5},
        ]
        service = self._make_service(records=records)
        users = await service.get_all()
        assert len(users) == 2
        assert all(isinstance(u, User) for u in users)

    @pytest.mark.asyncio
    async def test_exists_true(self) -> None:
        service = self._make_service(exists=True)
        assert await service.exists(1) is True

    @pytest.mark.asyncio
    async def test_exists_false(self) -> None:
        service = self._make_service(exists=False)
        assert await service.exists(999) is False

    @pytest.mark.asyncio
    async def test_link_calls_dao_create(self) -> None:
        service = self._make_service()
        await service.link(1, 10, 5)
        service._dao.create.assert_awaited_once_with(1, 10, 5)


class TestGroupRegistry:
    def _make_registry(self, keys=None, values=None):
        redis = MagicMock()
        redis.keys = AsyncMock(return_value=keys or [])
        redis.get = AsyncMock(side_effect=values or [])
        redis.set = AsyncMock()
        registry = GroupRegistry.__new__(GroupRegistry)
        registry._redis = redis
        return registry

    @pytest.mark.asyncio
    async def test_register_calls_set(self) -> None:
        registry = self._make_registry()
        await registry.register(5, 123456)
        registry._redis.set.assert_awaited_once_with("group_5", 123456)

    @pytest.mark.asyncio
    async def test_get_all_returns_dict(self) -> None:
        keys = [b"group_5", b"group_10"]
        values = [b"111", b"222"]
        registry = self._make_registry(keys=keys, values=values)
        result = await registry.get_all()
        assert result == {5: 111, 10: 222}

    @pytest.mark.asyncio
    async def test_get_all_empty(self) -> None:
        registry = self._make_registry()
        result = await registry.get_all()
        assert result == {}
