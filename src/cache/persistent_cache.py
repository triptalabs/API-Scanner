"""
Persistent cache implementation using SQLite.

This module provides a persistent cache layer using SQLite database
for long-term storage of cached data that survives application restarts.
"""

import asyncio
import sqlite3
import json
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta
from pathlib import Path

from ..async_core.base import AsyncContextManager
from ..async_core.interfaces import AsyncCacheManager
from ..async_core.exceptions import CacheError


class PersistentCache(AsyncContextManager, AsyncCacheManager):
    """
    Persistent cache using SQLite database.
    
    Provides durable caching with automatic cleanup of expired entries
    and efficient querying with proper indexing.
    """
    
    def __init__(
        self,
        db_path: str = "persistent_cache.db",
        default_ttl: int = 86400,  # 24 hours
        cleanup_interval: int = 3600  # 1 hour
    ) -> None:
        """
        Initialize persistent cache.
        
        Args:
            db_path: Path to SQLite database file
            default_ttl: Default TTL in seconds
            cleanup_interval: Interval for automatic cleanup in seconds
        """
        super().__init__()
        self.db_path = db_path
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        
        self.connection: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def _async_init(self) -> None:
        """Initialize persistent cache database."""
        # Ensure directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database connection
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0
        )
        
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA cache_size=10000")
        
        # Create tables and indexes
        await self._create_tables()
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        self.logger.debug(f"Persistent cache initialized: {self.db_path}")
    
    async def _async_close(self) -> None:
        """Close persistent cache."""
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close database connection
        if self.connection:
            self.connection.close()
            self.connection = None
        
        self.logger.debug("Persistent cache closed")
    
    async def _create_tables(self) -> None:
        """Create cache tables and indexes."""
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP,
                access_count INTEGER DEFAULT 1,
                last_accessed TIMESTAMP NOT NULL,
                data_size INTEGER DEFAULT 0
            )
        """)
        
        # Create indexes for efficient querying
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_expires_at 
            ON cache_entries(expires_at)
        """)
        
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_last_accessed 
            ON cache_entries(last_accessed)
        """)
        
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_created_at 
            ON cache_entries(created_at)
        """)
        
        self.connection.commit()
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from persistent cache.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[Any]: Cached value or None if not found/expired
        """
        async with self._lock:
            try:
                cursor = self.connection.execute("""
                    SELECT value, expires_at, access_count 
                    FROM cache_entries 
                    WHERE key = ?
                """, (key,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                value_json, expires_at_str, access_count = row
                
                # Check if expired
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now() > expires_at:
                        # Remove expired entry
                        await self._delete_key(key)
                        return None
                
                # Update access information
                self.connection.execute("""
                    UPDATE cache_entries 
                    SET access_count = ?, last_accessed = ?
                    WHERE key = ?
                """, (access_count + 1, datetime.now().isoformat(), key))
                
                self.connection.commit()
                
                # Deserialize value
                return json.loads(value_json)
                
            except Exception as e:
                raise CacheError(
                    f"Failed to get value from persistent cache: {e}",
                    operation="get",
                    cache_key=key
                )
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """
        Set value in persistent cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        if ttl is None:
            ttl = self.default_ttl
        
        expires_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
        
        async with self._lock:
            try:
                # Serialize value
                value_json = json.dumps(value)
                data_size = len(value_json.encode('utf-8'))
                
                now = datetime.now()
                
                # Insert or replace entry
                self.connection.execute("""
                    INSERT OR REPLACE INTO cache_entries 
                    (key, value, created_at, expires_at, access_count, last_accessed, data_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    key,
                    value_json,
                    now.isoformat(),
                    expires_at.isoformat() if expires_at else None,
                    1,
                    now.isoformat(),
                    data_size
                ))
                
                self.connection.commit()
                
            except Exception as e:
                raise CacheError(
                    f"Failed to set value in persistent cache: {e}",
                    operation="set",
                    cache_key=key
                )
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from persistent cache.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if key was deleted
        """
        async with self._lock:
            return await self._delete_key(key)
    
    async def _delete_key(self, key: str) -> bool:
        """Internal method to delete a key."""
        try:
            cursor = self.connection.execute(
                "DELETE FROM cache_entries WHERE key = ?", (key,)
            )
            self.connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            raise CacheError(
                f"Failed to delete key from persistent cache: {e}",
                operation="delete",
                cache_key=key
            )
    
    async def clear(self) -> None:
        """Clear all cached values."""
        async with self._lock:
            try:
                self.connection.execute("DELETE FROM cache_entries")
                self.connection.commit()
                self.logger.info("Persistent cache cleared")
            except Exception as e:
                raise CacheError(
                    f"Failed to clear persistent cache: {e}",
                    operation="clear"
                )
    
    async def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.
        
        Returns:
            int: Number of entries removed
        """
        async with self._lock:
            try:
                now = datetime.now().isoformat()
                cursor = self.connection.execute("""
                    DELETE FROM cache_entries 
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (now,))
                
                self.connection.commit()
                removed_count = cursor.rowcount
                
                if removed_count > 0:
                    self.logger.debug(f"Cleaned up {removed_count} expired entries")
                
                return removed_count
                
            except Exception as e:
                self.logger.error(f"Failed to cleanup expired entries: {e}")
                return 0
    
    async def _periodic_cleanup(self) -> None:
        """Periodic cleanup task for expired entries."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired()
                
                # Also vacuum database periodically (every 24 hours)
                if self.cleanup_interval >= 86400 or (
                    datetime.now().hour == 2 and datetime.now().minute < 5
                ):
                    await self._vacuum_database()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _vacuum_database(self) -> None:
        """Vacuum database to reclaim space."""
        async with self._lock:
            try:
                self.connection.execute("VACUUM")
                self.logger.debug("Database vacuumed")
            except Exception as e:
                self.logger.warning(f"Failed to vacuum database: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get persistent cache statistics."""
        async with self._lock:
            try:
                # Total entries
                cursor = self.connection.execute("SELECT COUNT(*) FROM cache_entries")
                total_entries = cursor.fetchone()[0]
                
                # Expired entries
                now = datetime.now().isoformat()
                cursor = self.connection.execute("""
                    SELECT COUNT(*) FROM cache_entries 
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (now,))
                expired_entries = cursor.fetchone()[0]
                
                # Total data size
                cursor = self.connection.execute("SELECT SUM(data_size) FROM cache_entries")
                total_size = cursor.fetchone()[0] or 0
                
                # Database file size
                db_file_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
                
                return {
                    'total_entries': total_entries,
                    'expired_entries': expired_entries,
                    'active_entries': total_entries - expired_entries,
                    'total_data_size_bytes': total_size,
                    'db_file_size_bytes': db_file_size,
                    'cleanup_interval_seconds': self.cleanup_interval
                }
                
            except Exception as e:
                self.logger.error(f"Failed to get cache stats: {e}")
                return {}
    
    async def get_keys(self, pattern: Optional[str] = None) -> List[str]:
        """
        Get all cache keys (excluding expired).
        
        Args:
            pattern: Optional SQL LIKE pattern to filter keys
            
        Returns:
            List[str]: List of cache keys
        """
        async with self._lock:
            try:
                now = datetime.now().isoformat()
                
                if pattern:
                    cursor = self.connection.execute("""
                        SELECT key FROM cache_entries 
                        WHERE (expires_at IS NULL OR expires_at > ?) 
                        AND key LIKE ?
                    """, (now, pattern))
                else:
                    cursor = self.connection.execute("""
                        SELECT key FROM cache_entries 
                        WHERE expires_at IS NULL OR expires_at > ?
                    """, (now,))
                
                return [row[0] for row in cursor.fetchall()]
                
            except Exception as e:
                self.logger.error(f"Failed to get cache keys: {e}")
                return []
    
    async def has_key(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        async with self._lock:
            try:
                now = datetime.now().isoformat()
                cursor = self.connection.execute("""
                    SELECT 1 FROM cache_entries 
                    WHERE key = ? AND (expires_at IS NULL OR expires_at > ?)
                """, (key, now))
                
                return cursor.fetchone() is not None
                
            except Exception as e:
                self.logger.error(f"Failed to check key existence: {e}")
                return False