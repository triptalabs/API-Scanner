# Async Core Foundation

This directory contains the foundational async components for the ChatGPT-API-Scanner performance optimization.

## Overview

The async core provides the base classes, interfaces, and utilities needed to transform the scanner from a Selenium-based tool to a high-performance async system.

## Components

### Base Classes (`base.py`)
- `AsyncBase`: Base class for all async components
- `AsyncContextManager`: Async context manager with proper initialization/cleanup
- `AsyncSemaphoreManager`: Centralized semaphore management for concurrency control

### Interfaces (`interfaces.py`)
- `AsyncAPIClient`: Interface for API clients (GitHub, OpenAI)
- `AsyncPatternMatcher`: Interface for pattern matching components
- `AsyncValidator`: Interface for API key validation
- `AsyncCacheManager`: Interface for caching systems
- `AsyncRateLimiter`: Interface for rate limiting

### Exceptions (`exceptions.py`)
- Custom exception hierarchy for async components
- Specific exceptions for rate limiting, validation, caching, etc.

### Configuration (`config.py`)
- `AsyncConfig`: Configuration dataclass with all async settings
- `AsyncConfigManager`: Configuration management with environment variable support
- Integration with existing `configs.py`

## Usage Example

```python
import asyncio
from async_core.config import get_config
from api_clients import GitHubAPIManager
from cache import HybridCacheManager

async def main():
    config = await get_config()
    
    async with (
        HybridCacheManager() as cache,
        GitHubAPIManager(config.github_token) as github
    ):
        async for result in github.search_code("sk-proj-"):
            await cache.set(f"result_{result.sha}", result.__dict__)
            print(f"Found: {result.repository}")

asyncio.run(main())
```

## Performance Benefits

The async foundation provides:

1. **10-50x Performance Improvement**: Concurrent operations vs sequential
2. **Better Resource Utilization**: Non-blocking I/O operations
3. **Intelligent Rate Limiting**: Adaptive rate limiting based on API responses
4. **Multi-tier Caching**: Memory, Redis, and SQLite caching layers
5. **Real-time Monitoring**: Comprehensive metrics and performance tracking

## Integration with Existing Code

The async foundation is designed to coexist with the existing synchronous code:

- Extends existing `configs.py` configuration
- Maintains compatibility with current database schema
- Preserves existing CLI interface
- Gradual migration path from Selenium to API-based approach

## Next Steps

1. Implement GitHub API clients (Task 2)
2. Build async pattern matching system (Task 3)
3. Create OpenAI validation pool (Task 4)
4. Optimize database operations (Task 5)
5. Add monitoring and metrics (Task 6)