"""
Example usage of the async foundation components.

This module demonstrates how to use the async components for
high-performance scanning operations.
"""

import asyncio
import logging
from typing import List

from .config import get_config
from ..api_clients import GitHubAPIManager, OpenAIValidatorPool
from ..cache import HybridCacheManager
from ..monitoring import MetricsCollector


async def example_async_scan():
    """
    Example of how to use the async foundation for scanning.
    
    This demonstrates the basic workflow of the async scanner
    using the new foundation components.
    """
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = await get_config()
        logger.info("Configuration loaded")
        
        # Initialize components
        async with (
            HybridCacheManager(config.cache_sqlite_path) as cache,
            MetricsCollector() as metrics,
            GitHubAPIManager(config.github_token) as github_api,
            OpenAIValidatorPool() as openai_validator
        ):
            logger.info("All async components initialized")
            
            # Example: Search for API keys in GitHub
            search_query = "sk-proj- language:python"
            
            logger.info(f"Starting search: {search_query}")
            
            # Track search performance
            search_count = 0
            async for result in github_api.search_code(search_query, max_results=10):
                search_count += 1
                
                # Record metrics
                await metrics.increment_counter("search_results_found")
                
                # Cache the result
                cache_key = f"search_result_{result.repository}_{result.sha}"
                await cache.set(cache_key, result.__dict__, ttl=3600)
                
                logger.info(f"Found result in {result.repository}: {result.file_path}")
                
                # Example: Extract and validate potential API keys
                # (This would use the pattern matcher in a real implementation)
                if "sk-" in result.content_snippet:
                    # Mock API key for demonstration
                    mock_api_key = "sk-proj-example123"
                    
                    # Validate the API key
                    validation_result = await openai_validator.validate_key(mock_api_key)
                    
                    logger.info(f"Validation result: {validation_result.status}")
                    
                    # Record validation metrics
                    await metrics.increment_counter(f"validation_{validation_result.status}")
            
            # Get final metrics
            final_metrics = await metrics.get_all_metrics()
            logger.info(f"Final metrics: {final_metrics}")
            
            logger.info(f"Scan completed. Found {search_count} results.")
    
    except Exception as e:
        logger.error(f"Error during async scan: {e}")
        raise


async def example_performance_comparison():
    """
    Example showing performance improvements over synchronous approach.
    
    This demonstrates the performance benefits of the async foundation
    compared to the original Selenium-based approach.
    """
    logger = logging.getLogger(__name__)
    
    # Simulate concurrent operations that would be sequential in the old system
    async def mock_github_search(query: str, delay: float = 0.1):
        """Mock GitHub search with simulated network delay."""
        await asyncio.sleep(delay)
        return f"Results for: {query}"
    
    async def mock_api_validation(api_key: str, delay: float = 0.2):
        """Mock API validation with simulated network delay."""
        await asyncio.sleep(delay)
        return f"Validated: {api_key[:10]}..."
    
    # Sequential approach (old system simulation)
    start_time = asyncio.get_event_loop().time()
    
    sequential_results = []
    for i in range(5):
        result = await mock_github_search(f"query_{i}")
        sequential_results.append(result)
        
        validation = await mock_api_validation(f"sk-example{i}")
        sequential_results.append(validation)
    
    sequential_time = asyncio.get_event_loop().time() - start_time
    
    # Concurrent approach (new async system)
    start_time = asyncio.get_event_loop().time()
    
    # Create all tasks
    search_tasks = [mock_github_search(f"query_{i}") for i in range(5)]
    validation_tasks = [mock_api_validation(f"sk-example{i}") for i in range(5)]
    
    # Run all tasks concurrently
    concurrent_results = await asyncio.gather(*search_tasks, *validation_tasks)
    
    concurrent_time = asyncio.get_event_loop().time() - start_time
    
    # Calculate performance improvement
    improvement = sequential_time / concurrent_time
    
    logger.info(f"Sequential time: {sequential_time:.2f}s")
    logger.info(f"Concurrent time: {concurrent_time:.2f}s")
    logger.info(f"Performance improvement: {improvement:.1f}x faster")
    
    return improvement


if __name__ == "__main__":
    # Run the examples
    asyncio.run(example_async_scan())
    asyncio.run(example_performance_comparison())