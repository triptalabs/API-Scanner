"""
Async core module for ChatGPT-API-Scanner performance optimization.

This module provides the foundational async components for the high-performance
version of the scanner, including base classes, interfaces, and core utilities.
"""

from .base import AsyncBase, AsyncContextManager
from .interfaces import (
    AsyncAPIClient,
    AsyncPatternMatcher,
    AsyncValidator,
    AsyncCacheManager,
    AsyncRateLimiter
)
from .exceptions import (
    AsyncScannerError,
    RateLimitError,
    ValidationError,
    CacheError
)

__all__ = [
    'AsyncBase',
    'AsyncContextManager',
    'AsyncAPIClient',
    'AsyncPatternMatcher',
    'AsyncValidator',
    'AsyncCacheManager',
    'AsyncRateLimiter',
    'AsyncScannerError',
    'RateLimitError',
    'ValidationError',
    'CacheError'
]