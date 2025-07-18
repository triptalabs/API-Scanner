"""
Interfaces and abstract base classes for async components.

This module defines the contracts that async components must implement,
ensuring consistent APIs across different implementations.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SearchResult:
    """Result from a GitHub code search."""
    repository: str
    file_path: str
    content_snippet: str
    line_number: int
    sha: str
    url: str
    timestamp: datetime


@dataclass
class APIKeyMatch:
    """Matched API key with metadata."""
    key: str
    pattern_type: str
    confidence_score: float
    context: str
    file_path: str
    line_number: int


@dataclass
class ValidationResult:
    """Result of API key validation."""
    key_hash: str
    status: str  # 'valid', 'invalid', 'expired', 'insufficient_quota', 'rate_limited'
    timestamp: datetime
    error_message: Optional[str] = None
    quota_info: Optional[Dict[str, Any]] = None


class AsyncAPIClient(ABC):
    """Abstract base class for async API clients."""
    
    @abstractmethod
    async def search_code(
        self, 
        query: str, 
        language: Optional[str] = None,
        max_results: int = 1000
    ) -> AsyncIterator[SearchResult]:
        """
        Search for code matching the query.
        
        Args:
            query: Search query string
            language: Programming language filter
            max_results: Maximum number of results to return
            
        Yields:
            SearchResult: Individual search results
        """
        pass
    
    @abstractmethod
    async def get_file_content(
        self, 
        repo: str, 
        path: str, 
        ref: str = "main"
    ) -> str:
        """
        Get content of a specific file.
        
        Args:
            repo: Repository identifier
            path: File path within repository
            ref: Git reference (branch, tag, commit)
            
        Returns:
            str: File content
        """
        pass
    
    @abstractmethod
    async def batch_search(
        self, 
        queries: List[str]
    ) -> AsyncIterator[SearchResult]:
        """
        Perform multiple searches concurrently.
        
        Args:
            queries: List of search queries
            
        Yields:
            SearchResult: Results from all queries
        """
        pass


class AsyncPatternMatcher(ABC):
    """Abstract base class for async pattern matching."""
    
    @abstractmethod
    async def find_matches(
        self, 
        content: str, 
        context: str = ""
    ) -> AsyncIterator[APIKeyMatch]:
        """
        Find API key patterns in content.
        
        Args:
            content: Text content to search
            context: Additional context for pattern matching
            
        Yields:
            APIKeyMatch: Matched API keys with metadata
        """
        pass
    
    @abstractmethod
    async def is_likely_false_positive(
        self, 
        key: str, 
        context: str
    ) -> bool:
        """
        Determine if a match is likely a false positive.
        
        Args:
            key: The matched API key
            context: Context around the match
            
        Returns:
            bool: True if likely false positive
        """
        pass


class AsyncValidator(ABC):
    """Abstract base class for async API key validation."""
    
    @abstractmethod
    async def validate_key(self, api_key: str) -> ValidationResult:
        """
        Validate a single API key.
        
        Args:
            api_key: The API key to validate
            
        Returns:
            ValidationResult: Validation result with status and metadata
        """
        pass
    
    @abstractmethod
    async def validate_batch(
        self, 
        api_keys: List[str]
    ) -> AsyncIterator[ValidationResult]:
        """
        Validate multiple API keys concurrently.
        
        Args:
            api_keys: List of API keys to validate
            
        Yields:
            ValidationResult: Individual validation results
        """
        pass


class AsyncCacheManager(ABC):
    """Abstract base class for async cache management."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Optional[Any]: Cached value or None if not found
        """
        pass
    
    @abstractmethod
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            bool: True if key was deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached values."""
        pass


class AsyncRateLimiter(ABC):
    """Abstract base class for async rate limiting."""
    
    @abstractmethod
    async def acquire(self, weight: float = 1.0) -> bool:
        """
        Acquire permission to make a request.
        
        Args:
            weight: Weight of the request (default 1.0)
            
        Returns:
            bool: True if permission granted
        """
        pass
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get rate limiter statistics.
        
        Returns:
            Dict[str, Any]: Statistics including current rate, tokens, etc.
        """
        pass
    
    @abstractmethod
    async def reset(self) -> None:
        """Reset the rate limiter state."""
        pass