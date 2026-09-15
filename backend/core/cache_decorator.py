from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Callable, Optional

from backend.core.cache import redis_cache


def cache_result(expire: int = 300):
    """
    Decorator to cache function results in Redis.
    
    Args:
        expire: Cache expiration time in seconds (default: 300 seconds/5 minutes)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            key_parts = [func.__name__]
            
            # Add positional arguments
            for arg in args:
                if isinstance(arg, (str, int, float, bool)):
                    key_parts.append(str(arg))
                elif isinstance(arg, (list, tuple)):
                    key_parts.append(json.dumps(arg, sort_keys=True))
                elif isinstance(arg, dict):
                    key_parts.append(json.dumps(arg, sort_keys=True))
                elif hasattr(arg, 'id') and isinstance(arg.id, (str, UUID)):
                    key_parts.append(str(arg.id))
                else:
                    # For complex objects, use their string representation
                    key_parts.append(str(arg))
            
            # Add keyword arguments
            for key, value in sorted(kwargs.items()):
                if isinstance(value, (str, int, float, bool)):
                    key_parts.append(f"{key}:{value}")
                elif isinstance(value, (list, tuple)):
                    key_parts.append(f"{key}:{json.dumps(value, sort_keys=True)}")
                elif isinstance(value, dict):
                    key_parts.append(f"{key}:{json.dumps(value, sort_keys=True)}")
                elif hasattr(value, 'id') and isinstance(value.id, (str, UUID)):
                    key_parts.append(f"{key}:{value.id}")
                else:
                    key_parts.append(f"{key}:{str(value)}")
            
            # Create a hash of the key parts to avoid key length issues
            key_string = "_".join(key_parts)
            cache_key = hashlib.md5(key_string.encode()).hexdigest()
            
            # Try to get from cache
            cached_result = await redis_cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Call the function and cache the result
            result = await func(*args, **kwargs)
            await redis_cache.set(cache_key, result, expire)
            
            return result
        return wrapper
    return decorator