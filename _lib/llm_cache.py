"""_lib/llm_cache.py — On-disk prompt hash cache for LLM responses.

Reduces repeated LLM calls by caching responses based on prompt + model hash.
Cache entries are stored as JSON files in a local cache directory.
Thread-safe with file locking.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from _lib.lock_utils import file_lock

# Default cache directory
_DEFAULT_CACHE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / ".llm_cache"
_DEFAULT_TTL_SECONDS = 3600  # 1 hour
_DEFAULT_MAX_ENTRIES = 1000


def _hash_key(messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
    """Generate a deterministic hash for the request.

    Args:
        messages: OpenAI-format message list.
        model: Model name.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.

    Returns:
        SHA-256 hex digest as cache key.
    """
    # Normalize messages: sort by role, truncate long content
    canonical: list[dict[str, Any]] = []
    for msg in sorted(messages, key=lambda m: str(m.get("role", "")) + str(m.get("content", ""))[:200]):
        canonical.append({
            "role": msg.get("role", ""),
            "content": str(msg.get("content", ""))[:500],  # Truncate very long prompts
        })

    payload = json.dumps({
        "messages": canonical,
        "model": model,
        "temperature": round(temperature, 2),
        "max_tokens": max_tokens,
    }, sort_keys=True, ensure_ascii=False)

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache:
    """On-disk prompt hash cache for LLM responses.

    Thread-safe via file locking. Automatic TTL eviction.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ):
        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0
        self._index_path = self._cache_dir / "_index.json"
        self._index: dict[str, float] = self._load_index()

    def _load_index(self) -> dict[str, float]:
        """Load the cache index from disk."""
        try:
            with file_lock(str(self._index_path) + ".lock", timeout=5):
                if self._index_path.exists():
                    with open(self._index_path, encoding="utf-8") as f:
                        return json.load(f)
        except (OSError, TimeoutError, json.JSONDecodeError):
            pass
        return {}

    def _save_index(self) -> None:
        """Save the cache index to disk atomically."""
        try:
            with file_lock(str(self._index_path) + ".lock", timeout=5):
                self._index_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = str(self._index_path) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._index, f, indent=2)
                os.replace(tmp, str(self._index_path))
        except (OSError, TimeoutError):
            pass

    def get(self, messages: list[dict], model: str, temperature: float = 0.7, max_tokens: int = 2048) -> str | None:
        """Get cached response for a given request.

        Args:
            messages: OpenAI-format message list.
            model: Model name.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.

        Returns:
            Cached response text, or None if not found or expired.
        """
        key = _hash_key(messages, model, temperature, max_tokens)
        now = time.time()

        # Check index
        expiry = self._index.get(key)
        if expiry is None or now > expiry:
            self._misses += 1
            return None

        # Check cache file
        cache_file = self._cache_dir / f"{key}.json"
        if not cache_file.exists():
            self._index.pop(key, None)
            self._misses += 1
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            self._hits += 1
            return data.get("response", "")
        except (json.JSONDecodeError, OSError):
            self._index.pop(key, None)
            self._misses += 1
            return None

    def set(
        self,
        response: str,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Cache a response for a given request.

        Args:
            response: Model response text.
            messages: OpenAI-format message list.
            model: Model name.
            temperature: Sampling temperature.
            max_tokens: Max output tokens.
            metadata: Optional metadata to store with the cache entry.
        """
        key = _hash_key(messages, model, temperature, max_tokens)
        now = time.time()

        # Evict old entries if at capacity
        if len(self._index) >= self._max_entries:
            self._evict_oldest()

        cache_file = self._cache_dir / f"{key}.json"
        try:
            cache_file.write_text(
                json.dumps({
                    "key": key,
                    "response": response,
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "created_at": now,
                    "expires_at": now + self._ttl,
                    "metadata": metadata or {},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            self._index[key] = now + self._ttl
            self._save_index()
        except OSError:
            pass

    def _evict_oldest(self) -> None:
        """Evict the oldest 10% of cache entries."""
        if not self._index:
            return
        sorted_keys = sorted(self._index.keys(), key=lambda k: self._index[k])
        evict_count = max(1, len(sorted_keys) // 10)
        for key in sorted_keys[:evict_count]:
            cache_file = self._cache_dir / f"{key}.json"
            with contextlib.suppress(OSError):
                cache_file.unlink(missing_ok=True)
            self._index.pop(key, None)
        self._save_index()

    def clear(self) -> None:
        """Clear all cache entries."""
        for key in list(self._index.keys()):
            cache_file = self._cache_dir / f"{key}.json"
            with contextlib.suppress(OSError):
                cache_file.unlink(missing_ok=True)
        self._index.clear()
        self._save_index()

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / (self._hits + self._misses), 4) if (self._hits + self._misses) > 0 else 0.0,
            "entries": len(self._index),
            "cache_dir": str(self._cache_dir),
            "ttl_seconds": self._ttl,
            "max_entries": self._max_entries,
        }


# Global singleton for shared use across the codebase
_default_cache: LLMCache | None = None


def get_cache() -> LLMCache:
    """Get the global LLM cache instance."""
    global _default_cache
    if _default_cache is None:
        _default_cache = LLMCache()
    return _default_cache


def cached_call(
    messages: list[dict],
    provider: str = "sensenova",
    model: str = "deepseek-v4-flash",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: int = 60,
    cache: LLMCache | None = None,
) -> str:
    """Call LLM with caching (cache hit returns immediately).

    Args:
        messages: OpenAI-format message list.
        provider: Provider name.
        model: Model name.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        timeout: Request timeout.
        cache: Optional LLMCache instance (defaults to global singleton).

    Returns:
        Response text (from cache or fresh LLM call).
    """
    from _lib.oc_llm_client import call_llm

    cache_instance = cache or get_cache()

    # Check cache
    cached = cache_instance.get(messages, model, temperature, max_tokens)
    if cached is not None:
        return cached

    # Call LLM
    response = call_llm(
        messages=messages,
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )

    # Cache the response
    if response:
        cache_instance.set(
            response=response,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            metadata={"provider": provider},
        )

    return response
