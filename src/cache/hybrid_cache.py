"""
Hybrid cache manager with multiple cache layers.

This module implements a multi-tier caching system with in-memory,
Redis, and persistent SQLite layers for optimal performance and
data persistence across different use cases.
"""

import asyncio
import json
import sqlite3
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

from ..async_core.base import AsyncContextManager
from ..async_core.interfaces import AsyncCacheManager
from ..async_core.exceptions import CacheError


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int
    last_accessed: datetime
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'key': self.key,
            'value': self.value,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'access_count': self.access_count,
            'last_accessed': self.last_accessed.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create from dictionary."""
        return cls(
            key=data['key'],
            value=data['value'],
            created_at=datetime.fromisoformat(data['created_at']),
            expires_at=datetime.fromisoformat(data['expires_at']) if data['expires_at'] else None,
            access_count=data['access_count'],
            last_accessed=datetime.fromisoformat(data['last_accessed'])
        )


class HybridCacheManager(AsyncContextManager, AsyncCacheManager):
    """
    Multi-tier cache manager with memory, Redis, and SQLite layers.
    
    Provides intelligent caching with automatic promotion/demotion
    between cache tiers based on access patterns and data importance.
    """
    
    def __init__(
        self,
        sqlite_path: str = "cache.db",
        redis_url: Optional[str] = None,
        max_memory_entries: int = 10000,
        default_ttl: int = 3600
    ) -> None:
        """
        Initialize hybrid cache manager.
        
        Args:
            sqlite_path: Path to SQLite cache database
            redis_url: Redis connection URL (optional)
            max_memory_entries: Maximum entries in memory cache
            default_ttl: Default TTL in seconds
        """
        super().__init__()
        self.sqlite_path = sqlite_path
        self.redis_url = redis_url
        self.max_memory_entries = max_memory_entries
        self.default_ttl = default_ttl
        
        # In-memory cache (Level 1)
        self.memory_cache: Dict[str, CacheEntry] = {}
        
        # Redis client (Level 2) - optional
        self.redis_client = None
        
        # SQLite connection (Level 3)
        self.sqlite_conn: Optional[sqlite3.Connection] = None
        
        self._lock = asyncio.Lock()
    
    async def _async_init(self) -> None:
        """Initialize cache layers."""
        # Initialize SQLite cache
        await self._init_sqlite()
        
        # Initialize Redis if URL provided
        if self.redis_url:
            await self._init_redis()
        
        self.logger.info("Hybrid cache manager initialized")
    
    async def _async_close(self) -> None:
        """Close cache connections."""
        if self.sqlite_conn:
            self.sqlite_conn.close()
            self.sqlite_conn = None
        
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
        
        self.logger.info("Hybrid cache manager closed")
    
    async def _init_sqlite(self) -> None:
        """Initialize SQLite cache database."""
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at TIMESTAMP,
                expires_at TIMESTAMP,
                access_count INTEGER,
                last_accessed TIMESTAMP
            )
        """)
        self.sqlite_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_expires_at 
            ON cache_entries(expires_at)
        """)
        self.sqlite_conn.commit()
        
        self.logger.debug("SQLite cache initialized")
    
    async def _init_redis(self) -> None:
        """Initialize Redis cache client."""
        try:
            import aioredis
            self.redis_client = aioredis.from_url(self.redis_url)
            # Test connection
            await self.redis_client.ping()
            self.logger.debug("Redis cache initialized")
        except ImportError:
            self.logger.warning("aioredis not available, Redis cache disabled")
            self.redis_client = None
        except Exception as e:
            self.logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache, checking all layers.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[Any]: Cached value or None if not found
        """
        async with self._lock:
            # Level 1: Memory cache
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                if not entry.is_expired():
                    entry.access_count += 1
                    entry.last_accessed = datetime.now()
                    self.logger.debug(f"Cache hit (memory): {key}")
                    return entry.value
                else:
                    # Remove expired entry
                    del self.memory_cache[key]
            
            # Level 2: Redis cache
            if self.redis_client:
                try:
                    cached_data = await self.redis_client.get(key)
                    if cached_data:
                        entry_dict = json.loads(cached_data)
                        entry = CacheEntry.from_dict(entry_dict)
                        
                        if not entry.is_expired():
                            # Promote to memory cache
                            await self._promote_to_memory(entry)
                            self.logger.debug(f"Cache hit (Redis): {key}")
                            return entry.value
                        else:
                            # Remove expired entry
                            await self.redis_client.delete(key)
                except Exception as e:
                    self.logger.warning(f"Redis get error for {key}: {e}")
            
            # Level 3: SQLite cache
            if self.sqlite_conn:
                try:
                    cursor = self.sqlite_conn.execute(
                        "SELECT * FROM cache_entries WHERE key = ?", (key,)
                    )
                    row = cursor.fetchone()
                    
                    if row:
                        entry_dict = {
                            'key': row[0],
                            'value': json.loads(row[1]),
                            'created_at': row[2],
                            'expires_at': row[3],
                            'access_count': row[4],
                            'last_accessed': row[5]
                        }
                        entry = CacheEntry.from_dict(entry_dict)
                        
                        if not entry.is_expired():
                            # Promote to higher cache levels
                            await self._promote_to_memory(entry)
                            if self.redis_client:
                                await self._promote_to_redis(entry)
                            
                            self.logger.debug(f"Cache hit (SQLite): {key}")
                            return entry.value
                        else:
                            # Remove expired entry
                            self.sqlite_conn.execute(
                                "DELETE FROM cache_entries WHERE key = ?", (key,)
                            )
                            self.sqlite_conn.commit()
                            
                except Exception as e:
                    self.logger.warning(f"SQLite get error for {key}: {e}")
        
        self.logger.debug(f"Cache miss: {key}")
        return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """
        Set value in cache across all layers.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        if ttl is None:
            ttl = self.default_ttl
        
        expires_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
        
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=datetime.now(),
            expires_at=expires_at,
            access_count=1,
            last_accessed=datetime.now()
        )
        
        async with self._lock:
            # Set in memory cache
            await self._set_in_memory(entry)
            
            # Set in Redis cache
            if self.redis_client:
                await self._set_in_redis(entry, ttl)
            
            # Set in SQLite cache
            if self.sqlite_conn:
                await self._set_in_sqlite(entry)
        
        self.logger.debug(f"Cache set: {key} (TTL: {ttl})")
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from all cache layers.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if key was deleted from any layer
        """
        deleted = False
        
        async with self._lock:
            # Delete from memory
            if key in self.memory_cache:
                del self.memory_cache[key]
                deleted = True
            
            # Delete from Redis
            if self.redis_client:
                try:
                    result = await self.redis_client.delete(key)
                    if result > 0:
                        deleted = True
                except Exception as e:
                    self.logger.warning(f"Redis delete error for {key}: {e}")
            
            # Delete from SQLite
            if self.sqlite_conn:
                try:
                    cursor = self.sqlite_conn.execute(
                        "DELETE FROM cache_entries WHERE key = ?", (key,)
                    )
                    if cursor.rowcount > 0:
                        deleted = True
                    self.sqlite_conn.commit()
                except Exception as e:
                    self.logger.warning(f"SQLite delete error for {key}: {e}")
        
        if deleted:
            self.logger.debug(f"Cache delete: {key}")
        
        return deleted
    
    async def clear(self) -> None:
        """Clear all cached values from all layers."""
        async with self._lock:
            # Clear memory cache
            self.memory_cache.clear()
            
            # Clear Redis cache
            if self.redis_client:
                try:
                    await self.redis_client.flushdb()
                except Exception as e:
                    self.logger.warning(f"Redis clear error: {e}")
            
            # Clear SQLite cache
            if self.sqlite_conn:
                try:
                    self.sqlite_conn.execute("DELETE FROM cache_entries")
                    self.sqlite_conn.commit()
                except Exception as e:
                    self.logger.warning(f"SQLite clear error: {e}")
        
        self.logger.info("All cache layers cleared")
    
    async def _promote_to_memory(self, entry: CacheEntry) -> None:
        """Promote entry to memory cache."""
        # Implement LRU eviction if memory cache is full
        if len(self.memory_cache) >= self.max_memory_entries:
            await self._evict_lru_from_memory()
        
        entry.access_count += 1
        entry.last_accessed = datetime.now()
        self.memory_cache[entry.key] = entry
    
    async def _promote_to_redis(self, entry: CacheEntry) -> None:
        """Promote entry to Redis cache."""
        if self.redis_client:
            try:
                ttl = None
                if entry.expires_at:
                    ttl = int((entry.expires_at - datetime.now()).total_seconds())
                    if ttl <= 0:
                        return
                
                await self._set_in_redis(entry, ttl)
            except Exception as e:
                self.logger.warning(f"Redis promotion error: {e}")
    
    async def _set_in_memory(self, entry: CacheEntry) -> None:
        """Set entry in memory cache."""
        if len(self.memory_cache) >= self.max_memory_entries:
            await self._evict_lru_from_memory()
        
        self.memory_cache[entry.key] = entry
    
    async def _set_in_redis(self, entry: CacheEntry, ttl: Optional[int]) -> None:
        """Set entry in Redis cache."""
        if self.redis_client:
            try:
                data = json.dumps(entry.to_dict())
                if ttl and ttl > 0:
                    await self.redis_client.setex(entry.key, ttl, data)
                else:
                    await self.redis_client.set(entry.key, data)
            except Exception as e:
                self.logger.warning(f"Redis set error: {e}")
    
    async def _set_in_sqlite(self, entry: CacheEntry) -> None:
        """Set entry in SQLite cache."""
        if self.sqlite_conn:
            try:
                self.sqlite_conn.execute("""
                    INSERT OR REPLACE INTO cache_entries 
                    (key, value, created_at, expires_at, access_count, last_accessed)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    entry.key,
                    json.dumps(entry.value),
                    entry.created_at.isoformat(),
                    entry.expires_at.isoformat() if entry.expires_at else None,
                    entry.access_count,
                    entry.last_accessed.isoformat()
                ))
                self.sqlite_conn.commit()
            except Exception as e:
                self.logger.warning(f"SQLite set error: {e}")
    
    async def _evict_lru_from_memory(self) -> None:
        """Evict least recently used entry from memory cache."""
        if not self.memory_cache:
            return
        
        # Find LRU entry
        lru_key = min(
            self.memory_cache.keys(),
            key=lambda k: self.memory_cache[k].last_accessed
        )
        
        # Remove from memory
        del self.memory_cache[lru_key]
        self.logger.debug(f"Evicted LRU entry from memory: {lru_key}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            'memory_entries': len(self.memory_cache),
            'max_memory_entries': self.max_memory_entries,
            'redis_available': self.redis_client is not None,
            'sqlite_available': self.sqlite_conn is not None
        }
        
        # Get SQLite stats
        if self.sqlite_conn:
            try:
                cursor = self.sqlite_conn.execute("SELECT COUNT(*) FROM cache_entries")
                stats['sqlite_entries'] = cursor.fetchone()[0]
            except Exception:
                stats['sqlite_entries'] = 0
        
        return stats