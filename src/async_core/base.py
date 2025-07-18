"""
Base classes for async components in ChatGPT-API-Scanner.

This module provides foundational async classes that other components inherit from,
ensuring consistent patterns and proper resource management.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class AsyncBase(ABC):
    """
    Base class for all async components in the scanner.
    
    Provides common functionality like logging, configuration access,
    and lifecycle management for async components.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize async base component.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialized = False
        self._closed = False
    
    async def initialize(self) -> None:
        """
        Initialize the async component.
        
        Override this method in subclasses to perform async initialization.
        """
        if self._initialized:
            return
        
        self.logger.debug(f"Initializing {self.__class__.__name__}")
        await self._async_init()
        self._initialized = True
        self.logger.debug(f"Initialized {self.__class__.__name__}")
    
    async def close(self) -> None:
        """
        Close and cleanup the async component.
        
        Override this method in subclasses to perform async cleanup.
        """
        if self._closed:
            return
        
        self.logger.debug(f"Closing {self.__class__.__name__}")
        await self._async_close()
        self._closed = True
        self.logger.debug(f"Closed {self.__class__.__name__}")
    
    @abstractmethod
    async def _async_init(self) -> None:
        """Subclass-specific async initialization."""
        pass
    
    @abstractmethod
    async def _async_close(self) -> None:
        """Subclass-specific async cleanup."""
        pass
    
    def __del__(self) -> None:
        """Ensure cleanup on garbage collection."""
        if not self._closed and hasattr(self, '_initialized'):
            self.logger.warning(
                f"{self.__class__.__name__} was not properly closed. "
                "Use async context manager or call close() explicitly."
            )


class AsyncContextManager(AsyncBase):
    """
    Async context manager base class.
    
    Provides async context manager functionality with proper initialization
    and cleanup for async components.
    """
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False


class AsyncSemaphoreManager:
    """
    Manager for controlling concurrency with semaphores.
    
    Provides centralized semaphore management for different types of operations
    to prevent resource exhaustion and respect rate limits.
    """
    
    def __init__(self) -> None:
        """Initialize semaphore manager."""
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()
    
    async def get_semaphore(self, name: str, limit: int) -> asyncio.Semaphore:
        """
        Get or create a semaphore for the given name and limit.
        
        Args:
            name: Semaphore identifier
            limit: Maximum concurrent operations
            
        Returns:
            asyncio.Semaphore: The semaphore for the given name
        """
        async with self._lock:
            if name not in self._semaphores:
                self._semaphores[name] = asyncio.Semaphore(limit)
            return self._semaphores[name]
    
    @asynccontextmanager
    async def acquire(self, name: str, limit: int):
        """
        Async context manager for acquiring semaphore.
        
        Args:
            name: Semaphore identifier
            limit: Maximum concurrent operations
        """
        semaphore = await self.get_semaphore(name, limit)
        async with semaphore:
            yield


# Global semaphore manager instance
semaphore_manager = AsyncSemaphoreManager()