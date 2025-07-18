"""
Test script to verify async foundation components are working correctly.

This script tests the basic functionality of all async foundation components
to ensure they are properly initialized and can work together.
"""

import asyncio
import logging
import tempfile
import os
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_async_foundation():
    """Test all async foundation components."""
    logger.info("Starting async foundation tests...")
    
    try:
        # Test 1: Import all async core components
        logger.info("Test 1: Testing imports...")
        from . import (
            AsyncBase, AsyncContextManager,
            AsyncAPIClient, AsyncPatternMatcher, AsyncValidator,
            AsyncCacheManager, AsyncRateLimiter,
            AsyncScannerError, RateLimitError, ValidationError, CacheError
        )
        from .config import AsyncConfigManager, get_config
        logger.info("✓ All async core imports successful")
        
        # Test 2: Import cache components
        logger.info("Test 2: Testing cache imports...")
        from ..cache import HybridCacheManager, MemoryCache, PersistentCache
        logger.info("✓ All cache imports successful")
        
        # Test 3: Import monitoring components
        logger.info("Test 3: Testing monitoring imports...")
        from ..monitoring import MetricsCollector, PerformanceMonitor, AdaptiveRateLimiter
        logger.info("✓ All monitoring imports successful")
        
        # Test 4: Test configuration management
        logger.info("Test 4: Testing configuration management...")
        config_manager = AsyncConfigManager()
        # Set a dummy GitHub token for testing
        os.environ['GITHUB_TOKEN'] = 'test_token_for_foundation_test'
        config = await config_manager.load_config()
        logger.info(f"✓ Configuration loaded: GitHub delay = {config.github_request_delay}s")
        # Clean up test token
        del os.environ['GITHUB_TOKEN']
        
        # Test 5: Test memory cache
        logger.info("Test 5: Testing memory cache...")
        async with MemoryCache(max_entries=100) as memory_cache:
            await memory_cache.set("test_key", "test_value", ttl=60)
            value = await memory_cache.get("test_key")
            assert value == "test_value", f"Expected 'test_value', got {value}"
            logger.info("✓ Memory cache working correctly")
        
        # Test 6: Test persistent cache
        logger.info("Test 6: Testing persistent cache...")
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            temp_db_path = temp_db.name
        
        try:
            async with PersistentCache(db_path=temp_db_path) as persistent_cache:
                await persistent_cache.set("persistent_key", {"data": "test"}, ttl=3600)
                value = await persistent_cache.get("persistent_key")
                assert value == {"data": "test"}, f"Expected dict, got {value}"
                logger.info("✓ Persistent cache working correctly")
        finally:
            # Clean up temp database
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)
        
        # Test 7: Test metrics collector (basic functionality only)
        logger.info("Test 7: Testing metrics collector...")
        # Create metrics collector without initializing background tasks
        metrics = MetricsCollector()
        
        # Test basic functionality directly
        await metrics.record_metric("test_metric", 42.0)
        await metrics.increment_counter("test_counter", 5)
        await metrics.set_gauge("test_gauge", 100.0)
        
        # Get stats without async lock issues
        counter_value = await metrics.get_counter_value("test_counter")
        gauge_value = await metrics.get_gauge_value("test_gauge")
        
        assert counter_value == 5, f"Expected counter value 5, got {counter_value}"
        assert gauge_value == 100.0, f"Expected gauge value 100.0, got {gauge_value}"
        logger.info("✓ Metrics collector working correctly")
        
        # Test 8: Test rate limiter
        logger.info("Test 8: Testing rate limiter...")
        from ..monitoring.rate_limiter import RateLimitConfig
        
        config = RateLimitConfig(
            requests_per_second=10.0,
            burst_capacity=20
        )
        
        async with AdaptiveRateLimiter("test_service", config) as rate_limiter:
            # Test acquiring tokens
            success = await rate_limiter.acquire(1.0)
            assert success, "Should be able to acquire token"
            
            # Record a successful request
            await rate_limiter.record_request(True, 0.1, 200)
            
            stats = await rate_limiter.get_stats()
            assert stats["total_requests"] == 1
            logger.info("✓ Rate limiter working correctly")
        
        # Test 9: Test hybrid cache (if Redis is available)
        logger.info("Test 9: Testing hybrid cache...")
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_cache_db:
            temp_cache_path = temp_cache_db.name
        
        try:
            async with HybridCacheManager(
                sqlite_path=temp_cache_path,
                redis_url=None,  # No Redis for this test
                max_memory_entries=100
            ) as hybrid_cache:
                await hybrid_cache.set("hybrid_key", "hybrid_value", ttl=60)
                value = await hybrid_cache.get("hybrid_key")
                assert value == "hybrid_value", f"Expected 'hybrid_value', got {value}"
                logger.info("✓ Hybrid cache working correctly")
        finally:
            # Clean up temp cache database
            if os.path.exists(temp_cache_path):
                os.unlink(temp_cache_path)
        
        logger.info("🎉 All async foundation tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the test with timeout
    try:
        success = asyncio.run(asyncio.wait_for(test_async_foundation(), timeout=30.0))
        exit(0 if success else 1)
    except asyncio.TimeoutError:
        logger.error("❌ Test timed out after 30 seconds")
        exit(1)