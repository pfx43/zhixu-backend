"""
异步缓存 — 给 async def 热路径用（SSE、打断检查、会话缓存）。

Memory 后端包装同一份同步 MemoryCache，与 def 路由共享数据。
Redis 后端用 redis.asyncio，避免在事件循环上阻塞。
def 路由继续用 app.core.redis.cache。
"""
from __future__ import annotations

import asyncio
from typing import Optional, Protocol


class AsyncCache(Protocol):
    async def get_value(self, key: str) -> Optional[str]: ...
    async def set_value(self, key: str, value: str, ttl: int | None = None) -> None: ...
    async def delete_key(self, key: str) -> None: ...
    async def expire(self, key: str, seconds: int) -> None: ...
    async def lpush(self, key: str, *values: str) -> int: ...
    async def rpush(self, key: str, *values: str) -> int: ...
    async def lrange(self, key: str, start: int, end: int) -> list[str]: ...
    async def lrem(self, key: str, count: int, value: str) -> int: ...


class MemoryAsyncCache:
    """委托给进程内 MemoryCache，无网络，await 立即返回。"""

    def __init__(self, sync_cache):
        self._sync = sync_cache

    async def get_value(self, key: str) -> Optional[str]:
        return self._sync.get_value(key)

    async def set_value(self, key: str, value: str, ttl: int | None = None) -> None:
        self._sync.set_value(key, value, ttl)

    async def delete_key(self, key: str) -> None:
        self._sync.delete_key(key)

    async def expire(self, key: str, seconds: int) -> None:
        self._sync.expire(key, seconds)

    async def lpush(self, key: str, *values: str) -> int:
        return self._sync.lpush(key, *values)

    async def rpush(self, key: str, *values: str) -> int:
        return self._sync.rpush(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return self._sync.lrange(key, start, end)

    async def lrem(self, key: str, count: int, value: str) -> int:
        return self._sync.lrem(key, count, value)


class RedisAsyncCache:
    """redis.asyncio 客户端，与同步 RedisCache 指向同一 REDIS_URL。

    连接绑在当前 running loop 上。TestClient / asyncio.run 会换 loop，
    因此按 loop 缓存客户端，避免 Future attached to a different loop。
    """

    def __init__(self, redis_url: str):
        import redis.asyncio as redis_async

        self._redis_async = redis_async
        self._url = redis_url
        self._clients: dict[asyncio.AbstractEventLoop, object] = {}

    def _client(self):
        loop = asyncio.get_running_loop()
        for stale in [item for item in self._clients if item.is_closed()]:
            self._clients.pop(stale, None)
        client = self._clients.get(loop)
        if client is None:
            client = self._redis_async.Redis.from_url(
                self._url, decode_responses=True
            )
            self._clients[loop] = client
        return client

    async def get_value(self, key: str) -> Optional[str]:
        return await self._client().get(key)

    async def set_value(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl is not None:
            await self._client().setex(key, ttl, value)
        else:
            await self._client().set(key, value)

    async def delete_key(self, key: str) -> None:
        await self._client().delete(key)

    async def expire(self, key: str, seconds: int) -> None:
        await self._client().expire(key, seconds)

    async def lpush(self, key: str, *values: str) -> int:
        return await self._client().lpush(key, *values)

    async def rpush(self, key: str, *values: str) -> int:
        return await self._client().rpush(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return list(await self._client().lrange(key, start, end))

    async def lrem(self, key: str, count: int, value: str) -> int:
        return await self._client().lrem(key, count, value)
