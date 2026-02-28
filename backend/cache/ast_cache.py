"""
cache/ast_cache.py

Thin wrapper around diskcache.Cache with a project-specific directory.
"""

from pathlib import Path
import diskcache

_CACHE_DIR = Path(__file__).parent.parent / ".ast_cache"
_cache_instance: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    global _cache_instance
    if _cache_instance is None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_instance = diskcache.Cache(str(_CACHE_DIR))
    return _cache_instance


def clear_cache() -> None:
    get_cache().clear()
