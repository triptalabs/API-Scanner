"""
In-memory cache implementation with LRU eviction.

This module provides a high-performance in-memory cache with
configurable size limits and LRU (Least Recently Used) eviction
policy for optimal memory usage.
"""

import asyncio
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from collections import OrderedDict

from ..async_core.base import AsyncContextManager
from ..async_core.interfaces import AsyncCacheManager
from ..async_core.exceptions import CacheError


class MemoryCache(AsyncContextManager, AsyncCacheManager):
    """
    High-performance in-memory cache with LRU eviction.
    
    Provides fast access to cached data with automatic eviction
    of least recently used entries when memory limits are reached.
    """
    
    def __init__(
        self,
        max_entries: int = 10000,
        default_ttl: int = 3600
    ) -> None:
        """
        Initialize memory cache.
        
        Args:
            max_entries: Maximum number of entries to store
            default_ttl: Default TTL in seconds
        """
        super().__init__()
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        
        # Use OrderedDict for LRU functionality
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
    
    async def _async_init(self) -> None:
        """Initialize memory cache."""
        self.logger.debug("Memory cache initialized")
    
    async def _async_close(self) -> None:
        """Close memory cache."""
        self._cache.clear()
        self.logger.debug("Memory cache closed")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from memory cache.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[Any]: Cached value or None if not found/expired
        """
        async with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            
            # Check if expired
            if self._is_expired(entry):
                del self._cache[key]
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            
            # Update access info
            entry['access_count'] += 1
            entry['last_accessed'] = datetime.now()
            
            return entry['value']
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """
        Set value in memory cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        if ttl is None:
            ttl = self.default_ttl
        
        expires_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
        
        entry = {
            'value': value,
            'created_at': datetime.now(),
            'expires_at': expires_at,
            'access_count': 1,
            'last_accessed': datetime.now()
        }
        
        async with self._lock:
            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]
            
            # Add new entry
            self._cache[key] = entry
            
            # Evict if over limit
            while len(self._cache) > self.max_entries:
                # Remove least recently used (first item)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self.logger.debug(f"Evicted LRU entry: {oldest_key}")
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from memory cache.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if key was deleted
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all cached values."""
        async with self._lock:
            self._cache.clear()
        
        self.logger.info("Memory cache cleared")
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired."""
        expires_at = entry.get('expires_at')
        if expires_at is None:
            return False
        return datetime.now() > expires_at
    
    async def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.
        
        Returns:
            int: Number of entries removed
        """
        removed_count = 0
        
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if self._is_expired(entry)
            ]
            
            for key in expired_keys:
                del self._cache[key]
                removed_count += 1
        
        if removed_count > 0:
            self.logger.debug(f"Cleaned up {removed_count} expired entries")
        
        return removed_count
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get memory cache statistics."""
        async with self._lock:
            total_entries = len(self._cache)
            expired_entries = sum(
                1 for entry in self._cache.values()
                if self._is_expired(entry)
            )
            
            return {
                'total_entries': total_entries,
                'expired_entries': expired_entries,
                'active_entries': total_entries - expired_entries,
                'max_entries': self.max_entries,
                'memory_usage_percent': (total_entries / self.max_entries) * 100
            }
    
    async def get_keys(self) -> list[str]:
        """Get all cache keys (excluding expired)."""
        async with self._lock:
            return [
                key for key, entry in self._cache.items()
                if not self._is_expired(entry)
            ]
    
    async def has_key(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        async with self._lock:
            if key not in self._cache:
                return False
            
            entry = self._cache[key]
            if self._is_expired(entry):
                del self._cache[key]
                return False
            
            return True