"""
Adaptive rate limiting system for API calls.

This module provides intelligent rate limiting with automatic adaptation
based on API responses, error rates, and system performance.
"""

import asyncio
import time
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import deque
import statistics

from ..async_core.base import AsyncContextManager
from ..async_core.interfaces import AsyncRateLimiter
from ..async_core.exceptions import RateLimitError


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_second: float
    burst_capacity: int
    backoff_multiplier: float = 2.0
    max_backoff: float = 300.0  # 5 minutes
    min_backoff: float = 1.0
    adaptation_enabled: bool = True


@dataclass
class RequestRecord:
    """Record of a request for rate limiting analysis."""
    timestamp: datetime
    success: bool
    response_time: float
    status_code: Optional[int] = None
    error_type: Optional[str] = None


class AdaptiveRateLimiter(AsyncContextManager, AsyncRateLimiter):
    """
    Adaptive rate limiter with intelligent backoff and optimization.
    
    Automatically adjusts rate limits based on API responses, error rates,
    and system performance to maximize throughput while respecting limits.
    """
    
    def __init__(
        self,
        service_name: str,
        initial_config: RateLimitConfig,
        max_history_size: int = 1000
    ) -> None:
        """
        Initialize adaptive rate limiter.
        
        Args:
            service_name: Name of the service being rate limited
            initial_config: Initial rate limit configuration
            max_history_size: Maximum number of request records to keep
        """
        super().__init__()
        self.service_name = service_name
        self.config = initial_config
        self.max_history_size = max_history_size
        
        # Token bucket state
        self.tokens = initial_config.burst_capacity
        self.last_refill = time.time()
        
        # Request history for adaptation
        self.request_history: deque[RequestRecord] = deque(maxlen=max_history_size)
        
        # Backoff state
        self.current_backoff = 0.0
        self.consecutive_errors = 0
        self.last_error_time: Optional[datetime] = None
        
        # Adaptation state
        self.last_adaptation = datetime.now()
        self.adaptation_interval = timedelta(minutes=5)
        
        # Statistics
        self.total_requests = 0
        self.total_errors = 0
        self.total_wait_time = 0.0
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def _async_init(self) -> None:
        """Initialize rate limiter."""
        self.logger.debug(f"Adaptive rate limiter initialized for {self.service_name}")
    
    async def _async_close(self) -> None:
        """Close rate limiter."""
        self.logger.debug(f"Adaptive rate limiter closed for {self.service_name}")
    
    async def acquire(self, weight: float = 1.0) -> bool:
        """
        Acquire permission to make a request.
        
        Args:
            weight: Weight of the request (default 1.0)
            
        Returns:
            bool: True if permission granted
        """
        async with self._lock:
            # Refill tokens based on time passed
            await self._refill_tokens()
            
            # Check if we have enough tokens
            if self.tokens >= weight:
                self.tokens -= weight
                return True
            
            # Calculate wait time
            tokens_needed = weight - self.tokens
            base_wait_time = tokens_needed / self.config.requests_per_second
            
            # Apply current backoff
            total_wait_time = base_wait_time + self.current_backoff
            
            # Record wait time
            self.total_wait_time += total_wait_time
            
            # Wait for tokens
            await asyncio.sleep(total_wait_time)
            
            # Refill tokens again after waiting
            await self._refill_tokens()
            
            # Deduct tokens
            self.tokens = max(0, self.tokens - weight)
            
            return True
    
    async def _refill_tokens(self) -> None:
        """Refill token bucket based on elapsed time."""
        now = time.time()
        time_passed = now - self.last_refill
        
        # Calculate tokens to add
        tokens_to_add = time_passed * self.config.requests_per_second
        
        # Add tokens up to burst capacity
        self.tokens = min(
            self.config.burst_capacity,
            self.tokens + tokens_to_add
        )
        
        self.last_refill = now
    
    async def record_request(
        self,
        success: bool,
        response_time: float,
        status_code: Optional[int] = None,
        error_type: Optional[str] = None
    ) -> None:
        """
        Record a request result for adaptation.
        
        Args:
            success: Whether the request was successful
            response_time: Response time in seconds
            status_code: HTTP status code
            error_type: Type of error if request failed
        """
        async with self._lock:
            # Create request record
            record = RequestRecord(
                timestamp=datetime.now(),
                success=success,
                response_time=response_time,
                status_code=status_code,
                error_type=error_type
            )
            
            # Add to history
            self.request_history.append(record)
            
            # Update statistics
            self.total_requests += 1
            if not success:
                self.total_errors += 1
                self.consecutive_errors += 1
                self.last_error_time = datetime.now()
            else:
                self.consecutive_errors = 0
            
            # Handle rate limit errors
            if status_code == 429 or error_type == "rate_limit":
                await self._handle_rate_limit_error()
            
            # Adapt rate limits if enabled
            if self.config.adaptation_enabled:
                await self._adapt_rate_limits()
    
    async def _handle_rate_limit_error(self) -> None:
        """Handle rate limit error by increasing backoff."""
        # Increase backoff exponentially
        if self.current_backoff == 0:
            self.current_backoff = self.config.min_backoff
        else:
            self.current_backoff = min(
                self.config.max_backoff,
                self.current_backoff * self.config.backoff_multiplier
            )
        
        # Reduce rate temporarily
        self.config.requests_per_second *= 0.5
        
        self.logger.warning(
            f"Rate limit hit for {self.service_name}. "
            f"Backoff: {self.current_backoff:.2f}s, "
            f"New rate: {self.config.requests_per_second:.2f} req/s"
        )
    
    async def _adapt_rate_limits(self) -> None:
        """Adapt rate limits based on recent performance."""
        now = datetime.now()
        
        # Only adapt periodically
        if now - self.last_adaptation < self.adaptation_interval:
            return
        
        self.last_adaptation = now
        
        # Get recent requests (last 10 minutes)
        recent_cutoff = now - timedelta(minutes=10)
        recent_requests = [
            r for r in self.request_history
            if r.timestamp >= recent_cutoff
        ]
        
        if len(recent_requests) < 10:  # Need sufficient data
            return
        
        # Calculate metrics
        success_rate = sum(1 for r in recent_requests if r.success) / len(recent_requests)
        avg_response_time = statistics.mean(r.response_time for r in recent_requests)
        
        # Adapt based on performance
        if success_rate > 0.95 and avg_response_time < 1.0:
            # Performance is good, can increase rate
            await self._increase_rate()
        elif success_rate < 0.8 or avg_response_time > 3.0:
            # Performance is poor, decrease rate
            await self._decrease_rate()
        elif self.consecutive_errors == 0 and self.current_backoff > 0:
            # No recent errors, can reduce backoff
            await self._reduce_backoff()
    
    async def _increase_rate(self) -> None:
        """Increase rate limit when performance is good."""
        old_rate = self.config.requests_per_second
        
        # Increase by 10% but don't exceed original rate * 1.5
        max_rate = self.config.requests_per_second * 1.5
        new_rate = min(max_rate, old_rate * 1.1)
        
        if new_rate > old_rate:
            self.config.requests_per_second = new_rate
            self.logger.debug(
                f"Increased rate for {self.service_name}: "
                f"{old_rate:.2f} -> {new_rate:.2f} req/s"
            )
    
    async def _decrease_rate(self) -> None:
        """Decrease rate limit when performance is poor."""
        old_rate = self.config.requests_per_second
        
        # Decrease by 20% but don't go below 10% of original
        min_rate = self.config.requests_per_second * 0.1
        new_rate = max(min_rate, old_rate * 0.8)
        
        if new_rate < old_rate:
            self.config.requests_per_second = new_rate
            self.logger.debug(
                f"Decreased rate for {self.service_name}: "
                f"{old_rate:.2f} -> {new_rate:.2f} req/s"
            )
    
    async def _reduce_backoff(self) -> None:
        """Reduce backoff when there are no recent errors."""
        if self.current_backoff > 0:
            old_backoff = self.current_backoff
            self.current_backoff = max(0, self.current_backoff * 0.5)
            
            if self.current_backoff < self.config.min_backoff:
                self.current_backoff = 0
            
            self.logger.debug(
                f"Reduced backoff for {self.service_name}: "
                f"{old_backoff:.2f}s -> {self.current_backoff:.2f}s"
            )
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get rate limiter statistics.
        
        Returns:
            Dict[str, Any]: Statistics including current rate, tokens, etc.
        """
        async with self._lock:
            # Calculate recent error rate
            recent_cutoff = datetime.now() - timedelta(minutes=10)
            recent_requests = [
                r for r in self.request_history
                if r.timestamp >= recent_cutoff
            ]
            
            recent_error_rate = 0.0
            if recent_requests:
                recent_errors = sum(1 for r in recent_requests if not r.success)
                recent_error_rate = recent_errors / len(recent_requests)
            
            # Calculate average response time
            avg_response_time = 0.0
            if recent_requests:
                avg_response_time = statistics.mean(r.response_time for r in recent_requests)
            
            return {
                "service_name": self.service_name,
                "current_rate_per_second": self.config.requests_per_second,
                "burst_capacity": self.config.burst_capacity,
                "current_tokens": self.tokens,
                "current_backoff_seconds": self.current_backoff,
                "consecutive_errors": self.consecutive_errors,
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "total_error_rate": self.total_errors / max(1, self.total_requests),
                "recent_error_rate": recent_error_rate,
                "average_response_time": avg_response_time,
                "total_wait_time_seconds": self.total_wait_time,
                "adaptation_enabled": self.config.adaptation_enabled,
                "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None
            }
    
    async def reset(self) -> None:
        """Reset the rate limiter state."""
        async with self._lock:
            self.tokens = self.config.burst_capacity
            self.last_refill = time.time()
            self.current_backoff = 0.0
            self.consecutive_errors = 0
            self.last_error_time = None
            self.request_history.clear()
            
            # Reset statistics
            self.total_requests = 0
            self.total_errors = 0
            self.total_wait_time = 0.0
            
            self.logger.info(f"Rate limiter reset for {self.service_name}")
    
    async def set_rate(self, requests_per_second: float) -> None:
        """
        Manually set the rate limit.
        
        Args:
            requests_per_second: New rate limit
        """
        async with self._lock:
            old_rate = self.config.requests_per_second
            self.config.requests_per_second = requests_per_second
            
            self.logger.info(
                f"Rate limit manually set for {self.service_name}: "
                f"{old_rate:.2f} -> {requests_per_second:.2f} req/s"
            )
    
    async def get_wait_time(self, weight: float = 1.0) -> float:
        """
        Get estimated wait time for a request.
        
        Args:
            weight: Weight of the request
            
        Returns:
            float: Estimated wait time in seconds
        """
        async with self._lock:
            await self._refill_tokens()
            
            if self.tokens >= weight:
                return 0.0
            
            tokens_needed = weight - self.tokens
            base_wait_time = tokens_needed / self.config.requests_per_second
            
            return base_wait_time + self.current_backoff


class RateLimiterManager:
    """
    Manager for multiple rate limiters.
    
    Provides centralized management of rate limiters for different services
    with shared configuration and monitoring.
    """
    
    def __init__(self) -> None:
        """Initialize rate limiter manager."""
        self.rate_limiters: Dict[str, AdaptiveRateLimiter] = {}
        self._lock = asyncio.Lock()
    
    async def get_rate_limiter(
        self,
        service_name: str,
        config: Optional[RateLimitConfig] = None
    ) -> AdaptiveRateLimiter:
        """
        Get or create a rate limiter for a service.
        
        Args:
            service_name: Name of the service
            config: Rate limit configuration (uses default if None)
            
        Returns:
            AdaptiveRateLimiter: Rate limiter for the service
        """
        async with self._lock:
            if service_name not in self.rate_limiters:
                if config is None:
                    # Default configuration
                    config = RateLimitConfig(
                        requests_per_second=10.0,
                        burst_capacity=20
                    )
                
                rate_limiter = AdaptiveRateLimiter(service_name, config)
                await rate_limiter.initialize()
                self.rate_limiters[service_name] = rate_limiter
            
            return self.rate_limiters[service_name]
    
    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all rate limiters.
        
        Returns:
            Dict[str, Dict[str, Any]]: Statistics for each service
        """
        async with self._lock:
            stats = {}
            for service_name, rate_limiter in self.rate_limiters.items():
                stats[service_name] = await rate_limiter.get_stats()
            return stats
    
    async def reset_all(self) -> None:
        """Reset all rate limiters."""
        async with self._lock:
            for rate_limiter in self.rate_limiters.values():
                await rate_limiter.reset()
    
    async def close_all(self) -> None:
        """Close all rate limiters."""
        async with self._lock:
            for rate_limiter in self.rate_limiters.values():
                await rate_limiter.close()
            self.rate_limiters.clear()


# Global rate limiter manager instance
rate_limiter_manager = RateLimiterManager()