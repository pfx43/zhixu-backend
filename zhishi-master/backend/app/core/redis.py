import fnmatch
import json
import time


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


cache = MemoryCache()
