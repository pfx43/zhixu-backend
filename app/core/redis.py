import fnmatch
import json
import os
import time

import redis


class MemoryCache:
    """进程内缓存，用于 auth token、验证码、聊天历史等。"""

    def __init__(self):
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lists: dict[str, list[str]] = {}

    def _purge_expired_key(self, key: str) -> None:
        if key not in self._data:
            return
        _, expiry = self._data[key]
        if expiry is not None and time.monotonic() > expiry:
            del self._data[key]

    def _purge_expired(self) -> None:
        for key in list(self._data.keys()):
            self._purge_expired_key(key)

    def set_session(self, token: str, user_data: dict, ttl: int = 604800):
        self.set_value(f"auth:token:{token}", json.dumps(user_data), ttl)

    def get_session(self, token: str):
        data = self.get_value(f"auth:token:{token}")
        return json.loads(data) if data else None

    def set_value(self, key: str, value: str, ttl: int = None):
        expiry = (time.monotonic() + ttl) if ttl is not None else None
        self._data[key] = (value, expiry)

    def get_value(self, key: str):
        self._purge_expired_key(key)
        if key not in self._data:
            return None
        return self._data[key][0]

    def delete_key(self, key: str):
        self._data.pop(key, None)
        self._lists.pop(key, None)

    def scan_keys(self, pattern: str):
        self._purge_expired()
        seen: set[str] = set()
        for key in list(self._data.keys()) + list(self._lists.keys()):
            if key in seen:
                continue
            if fnmatch.fnmatch(key, pattern):
                seen.add(key)
                yield key

    def lpush(self, key: str, *values):
        self._lists.setdefault(key, [])
        for value in reversed(values):
            self._lists[key].insert(0, value)
        return len(self._lists[key])

    def rpush(self, key: str, *values):
        self._lists.setdefault(key, []).extend(values)
        return len(self._lists[key])

    def lrange(self, key: str, start: int, end: int):
        items = self._lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    def lrem(self, key: str, count: int, value: str):
        items = self._lists.get(key, [])
        removed = 0
        if count == 0:
            while value in items:
                items.remove(value)
                removed += 1
        elif count > 0:
            for item in items[:count]:
                if item == value:
                    items.remove(value)
                    removed += 1
        else:
            for item in reversed(items):
                if removed >= abs(count):
                    break
                if item == value:
                    items.remove(value)
                    removed += 1
        return removed

    # ── 原子计数器（TinaGateway Key 池 / 用户并发用） ──

    def incr(self, key: str, amount: int = 1) -> int:
        """递增计数器，返回递增后的值。"""
        current = self.get_value(key)
        val = int(current) + amount if current else amount
        self.set_value(key, str(val))
        return val

    def decr(self, key: str, amount: int = 1) -> int:
        """递减计数器，返回递减后的值。"""
        current = self.get_value(key)
        val = int(current) - amount if current else -amount
        self.set_value(key, str(val))
        return val

    def expire(self, key: str, seconds: int) -> None:
        """设置 key 的过期时间（MemoryCache 通过 set_value 的 ttl 已支持，此处为兼容接口）。"""
        val = self.get_value(key)
        if val is not None:
            self.set_value(key, val, ttl=seconds)

    # ── ZSET 操作（仅 Redis 支持，MemoryCache 返回安全默认值） ──

    def zadd(self, key: str, mapping: dict) -> int:
        """ZSET 添加（MemoryCache 降级为无操作）。"""
        return 0

    def zcard(self, key: str) -> int:
        """ZSET 基数（MemoryCache 始终返回 0 = 不限 RPM）。"""
        return 0

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        """ZSET 按分数范围删除（MemoryCache 降级为无操作）。"""
        return 0


class RedisCache:
    """Redis 缓存，用于生产环境。

    方法与 MemoryCache 对齐，调用方无需感知底层实现。
    """

    def __init__(self, redis_url: str):
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def set_session(self, token: str, user_data: dict, ttl: int = 604800):
        self.set_value(f"auth:token:{token}", json.dumps(user_data), ttl)

    def get_session(self, token: str):
        data = self.get_value(f"auth:token:{token}")
        return json.loads(data) if data else None

    def set_value(self, key: str, value: str, ttl: int = None):
        if ttl is not None:
            self._client.setex(key, ttl, value)
        else:
            self._client.set(key, value)

    def get_value(self, key: str):
        return self._client.get(key)

    def delete_key(self, key: str):
        self._client.delete(key)

    def scan_keys(self, pattern: str):
        """使用 SCAN 遍历 key，客户端侧 fnmatch 过滤。

        注意：fnmatch 与 Redis 的 glob 风格略有差异（如 [chars] 语法），
        生产若需要完全一致的行为可改为使用 KEYS 配合哨兵或 lua 脚本。
        """
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match="*", count=100)
            for key in keys:
                if fnmatch.fnmatch(key, pattern):
                    yield key
            if cursor == 0:
                break

    def lpush(self, key: str, *values):
        return self._client.lpush(key, *values)

    def rpush(self, key: str, *values):
        return self._client.rpush(key, *values)

    def lrange(self, key: str, start: int, end: int):
        return self._client.lrange(key, start, end)

    def lrem(self, key: str, count: int, value: str):
        return self._client.lrem(key, count, value)

    # ── 原子计数器（TinaGateway Key 池 / 用户并发用） ──

    def incr(self, key: str, amount: int = 1) -> int:
        """递增计数器，返回递增后的值。"""
        return self._client.incrby(key, amount)

    def decr(self, key: str, amount: int = 1) -> int:
        """递减计数器，返回递减后的值。"""
        return self._client.decrby(key, amount)

    def expire(self, key: str, seconds: int) -> None:
        """设置 key 的过期时间（秒）。"""
        self._client.expire(key, seconds)

    # ── ZSET 操作（RPM 滑动窗口） ──

    def zadd(self, key: str, mapping: dict) -> int:
        """ZSET 添加成员。"""
        return self._client.zadd(key, mapping)

    def zcard(self, key: str) -> int:
        """ZSET 基数。"""
        return self._client.zcard(key)

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        """ZSET 按分数范围删除。"""
        return self._client.zremrangebyscore(key, min_score, max_score)


# 模块级缓存实例，按 CACHE_BACKEND 切换

CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

if CACHE_BACKEND == "redis":
    cache = RedisCache(REDIS_URL)
else:
    cache = MemoryCache()