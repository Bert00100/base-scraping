from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

DEFAULT_CACHE_DIR = Path(".cache/basecnpj")
DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30 dias — dado cadastral muda pouco
NO_CACHE_ROUTES = frozenset({"status"})  # preflight deve ser sempre fresco


def _cache_key(route: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"route": route, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_path(cache_dir: Path, route: str, params: dict[str, Any]) -> Path:
    return cache_dir / f"{_cache_key(route, params)}.json"


def read_cache(
    route: str,
    params: dict[str, Any],
    *,
    cache_dir: Path | None = None,
    ttl: float = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> dict[str, Any] | None:
    if route in NO_CACHE_ROUTES:
        return None
    path = _cache_path(cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR, route, params)
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    current = time.time() if now is None else now
    if current - entry.get("cached_at", 0) > ttl:
        return None
    return entry.get("data")


def write_cache(
    route: str,
    params: dict[str, Any],
    data: dict[str, Any],
    *,
    cache_dir: Path | None = None,
    now: float | None = None,
) -> None:
    if route in NO_CACHE_ROUTES:
        return
    cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, route, params)
    entry = {"cached_at": time.time() if now is None else now, "data": data}
    path.write_text(json.dumps(entry))


async def get_or_fetch(
    route: str,
    params: dict[str, Any],
    fetch: Callable[[], Awaitable[dict[str, Any]]],
    *,
    cache_dir: Path | None = None,
    ttl: float = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Serve do cache em disco se existir e estiver dentro do TTL; senão chama `fetch` e grava."""
    cached = read_cache(route, params, cache_dir=cache_dir, ttl=ttl, now=now)
    if cached is not None:
        return cached
    data = await fetch()
    write_cache(route, params, data, cache_dir=cache_dir, now=now)
    return data
