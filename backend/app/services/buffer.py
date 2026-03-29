import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()


class RedisFifoBuffer:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _key(session_id: str) -> str:
        return f'live-buffer:{session_id}'

    async def enqueue(self, session_id: str, payload: dict[str, Any]) -> None:
        await self.redis.rpush(self._key(session_id), json.dumps(payload, ensure_ascii=False))

    async def consume(self, session_id: str, timeout: int = 1) -> dict[str, Any] | None:
        item = await self.redis.blpop(self._key(session_id), timeout=timeout)
        if item is None:
            return None
        _, raw = item
        return json.loads(raw)
