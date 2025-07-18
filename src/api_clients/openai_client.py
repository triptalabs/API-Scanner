"""
OpenAI API client for async key validation.

This module provides async validation of OpenAI API keys, replacing
the ThreadPoolExecutor-based approach with proper async concurrency
and connection pooling.
"""

import asyncio
import hashlib
from typing import List, AsyncIterator, Dict, Any, Optional
from datetime import datetime

from .base_client import BaseAsyncClient
from ..async_core.interfaces import AsyncValidator, ValidationResult
from ..async_core.exceptions import ValidationError, RateLimitError
from ..async_core.base import semaphore_manager


class OpenAIValidatorPool(BaseAsyncClient, AsyncValidator):
    """
    Async OpenAI API key validator with connection pooling.
    
    Provides concurrent validation of OpenAI API keys with proper
    rate limiting, error handling, and result caching.
    """
    
    def __init__(
        self, 
        max_concurrent: int = 20,
        requests_per_minute: int = 50,
        **kwargs
    ) -> None:
        """
        Initialize OpenAI validator pool.
        
        Args:
            max_concurrent: Maximum concurrent validations
            requests_per_minute: Rate limit for requests per minute
            **kwargs: Additional arguments for BaseAsyncClient
        """
        headers = {
            'User-Agent': 'ChatGPT-API-Scanner/2.0',
            'Content-Type': 'application/json'
        }
        
        super().__init__(
            base_url='https://api.openai.com/v1',
            headers=headers,
            **kwargs
        )
        
        self.max_concurrent = max_concurrent
        self.requests_per_minute = requests_per_minute
        self.request_times: List[datetime] = []
        self.validation_cache: Dict[str, ValidationResult] = {}
        self.cache_ttl = 3600  # 1 hour cache TTL
    
    def _get_key_hash(self, api_key: str) -> str:
        """
        Get hash of API key for logging and caching.
        
        Args:
            api_key: The API key to hash
            
        Returns:
            str: SHA-256 hash of the key (first 16 characters)
        """
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]
    
    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        now = datetime.now()
        
        # Remove requests older than 1 minute
        self.request_times = [
            req_time for req_time in self.request_times
            if (now - req_time).total_seconds() < 60
        ]
        
        # Check if we're at the rate limit
        if len(self.request_times) >= self.requests_per_minute:
            oldest_request = min(self.request_times)
            wait_time = 60 - (now - oldest_request).total_seconds()
            
            if wait_time > 0:
                self.logger.info(f"Rate limit reached, waiting {wait_time:.1f} seconds")
                await asyncio.sleep(wait_time)
        
        # Record this request
        self.request_times.append(now)
    
    async def validate_key(self, api_key: str) -> ValidationResult:
        """
        Validate a single OpenAI API key.
        
        Args:
            api_key: The API key to validate
            
        Returns:
            ValidationResult: Validation result with status and metadata
        """
        key_hash = self._get_key_hash(api_key)
        
        # Check cache first
        if key_hash in self.validation_cache:
            cached_result = self.validation_cache[key_hash]
            cache_age = (datetime.now() - cached_result.timestamp).total_seconds()
            
            if cache_age < self.cache_ttl:
                self.logger.debug(f"Using cached result for key {key_hash}")
                return cached_result
            else:
                # Remove expired cache entry
                del self.validation_cache[key_hash]
        
        # Enforce rate limiting
        await self._check_rate_limit()
        
        # Use semaphore to limit concurrent validations
        async with semaphore_manager.acquire('openai_validation', self.max_concurrent):
            try:
                # Make request to OpenAI API
                headers = {'Authorization': f'Bearer {api_key}'}
                
                # Use models endpoint for validation (lightweight)
                response = await self.get('/models', headers=headers)
                
                # If we get here, the key is valid
                result = ValidationResult(
                    key_hash=key_hash,
                    status='valid',
                    timestamp=datetime.now(),
                    quota_info=self._extract_quota_info(response)
                )
                
                self.logger.info(f"Key {key_hash} validated successfully")
                
            except RateLimitError as e:
                result = ValidationResult(
                    key_hash=key_hash,
                    status='rate_limited',
                    timestamp=datetime.now(),
                    error_message=str(e)
                )
                
                self.logger.warning(f"Rate limited while validating key {key_hash}")
                
            except ValidationError as e:
                if e.details.get('status_code') == 401:
                    status = 'invalid'
                elif e.details.get('status_code') == 429:
                    status = 'rate_limited'
                else:
                    status = 'unknown'
                
                result = ValidationResult(
                    key_hash=key_hash,
                    status=status,
                    timestamp=datetime.now(),
                    error_message=str(e)
                )
                
                self.logger.info(f"Key {key_hash} validation failed: {status}")
                
            except Exception as e:
                result = ValidationResult(
                    key_hash=key_hash,
                    status='unknown',
                    timestamp=datetime.now(),
                    error_message=str(e)
                )
                
                self.logger.error(f"Unexpected error validating key {key_hash}: {e}")
        
        # Cache the result
        self.validation_cache[key_hash] = result
        
        return result
    
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
        # Create validation tasks
        tasks = [self.validate_key(key) for key in api_keys]
        
        # Process tasks as they complete
        for coro in asyncio.as_completed(tasks):
            try:
                result = await coro
                yield result
            except Exception as e:
                self.logger.error(f"Error in batch validation: {e}")
                # Yield error result
                yield ValidationResult(
                    key_hash='unknown',
                    status='error',
                    timestamp=datetime.now(),
                    error_message=str(e)
                )
    
    def _extract_quota_info(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract quota information from API response.
        
        Args:
            response: API response data
            
        Returns:
            Dict[str, Any]: Quota information
        """
        # Extract quota info from response headers or body
        # This would depend on OpenAI's API response format
        return {
            'models_available': len(response.get('data', [])),
            'timestamp': datetime.now().isoformat()
        }
    
    async def get_validation_stats(self) -> Dict[str, Any]:
        """
        Get validation statistics.
        
        Returns:
            Dict[str, Any]: Statistics about validations performed
        """
        now = datetime.now()
        recent_requests = [
            req_time for req_time in self.request_times
            if (now - req_time).total_seconds() < 300  # Last 5 minutes
        ]
        
        cache_stats = {
            'total_cached': len(self.validation_cache),
            'cache_hit_rate': 0.0  # Would need to track hits vs misses
        }
        
        return {
            'requests_last_minute': len([
                req_time for req_time in self.request_times
                if (now - req_time).total_seconds() < 60
            ]),
            'requests_last_5_minutes': len(recent_requests),
            'cache_stats': cache_stats,
            'rate_limit': self.requests_per_minute,
            'max_concurrent': self.max_concurrent
        }