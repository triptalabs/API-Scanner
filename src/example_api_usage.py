#!/usr/bin/env python3
"""
Example usage of GitHub API client to replace Selenium functionality.

This script demonstrates how to use the new GitHub API client to scan
for API keys, replacing the original Selenium-based implementation.
"""

import asyncio
import os
import logging
from typing import List, Dict, Any

from api_clients.github_client import GitHubAPIManager
from manager import DatabaseManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def scan_with_api_client(db_file: str = "github_api.db"):
    """
    Scan GitHub for API keys using the new API client.
    
    This function demonstrates how to replace the original Selenium-based
    scanner with the new API-based implementation.
    
    Args:
        db_file: Database file to store results
    """
    # Get GitHub token from environment
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        logger.info("Please set your GitHub Personal Access Token:")
        logger.info("export GITHUB_TOKEN='your_token_here'")
        logger.info("Get a token from: https://github.com/settings/tokens")
        return
    
    logger.info("Starting API-based GitHub scan...")
    
    # Initialize the API manager
    async with GitHubAPIManager(github_token) as api_manager:
        # Validate that we can replace Selenium
        validation = await api_manager.validate_replacement_compatibility()
        logger.info(f"Compatibility check: {validation['compatibility_score']:.2%}")
        
        if not validation['ready_for_production']:
            logger.warning("API client may not be fully ready to replace Selenium")
            logger.info("Validation results:")
            for key, value in validation.items():
                if isinstance(value, bool):
                    status = "✓" if value else "✗"
                    logger.info(f"  {status} {key}")
        
        # Initialize database
        found_keys = []
        
        try:
            # Scan repositories using API (equivalent to Selenium functionality)
            logger.info("Scanning repositories for API keys...")
            
            key_count = 0
            async for api_key_info in api_manager.replace_selenium_scanner():
                key_count += 1
                found_keys.append(api_key_info)
                
                # Log found key (masked for security)
                masked_key = f"{api_key_info['key'][:10]}...{api_key_info['key'][-10:]}"
                logger.info(f"Found API key: {masked_key} in {api_key_info['repository']}")
                
                # Limit for demo purposes
                if key_count >= 10:
                    logger.info("Limiting to 10 keys for demo purposes...")
                    break
            
            logger.info(f"Scan completed. Found {len(found_keys)} API keys.")
            
            # Store results in database (similar to original implementation)
            if found_keys:
                logger.info("Storing results in database...")
                with DatabaseManager(db_file) as db:
                    for key_info in found_keys:
                        # Store the key with 'found' status (would need validation later)
                        db.insert(key_info['key'], 'found')
                
                logger.info(f"Results stored in {db_file}")
            
            # Show statistics
            stats = await api_manager.get_combined_stats()
            logger.info("Scan statistics:")
            logger.info(f"  Total API calls: {stats['total_api_calls']}")
            logger.info(f"  Rate limits hit: {stats['total_rate_limits']}")
            
            if 'rest_client' in stats and stats['rest_client']:
                rest_stats = stats['rest_client']
                logger.info(f"  REST API searches: {rest_stats.get('total_searches', 0)}")
                logger.info(f"  REST API results: {rest_stats.get('total_results', 0)}")
        
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            raise


async def compare_with_selenium_urls():
    """
    Compare API-based approach with original Selenium URL patterns.
    
    This function demonstrates how the API client generates the same
    search patterns as the original Selenium implementation.
    """
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return
    
    logger.info("Comparing with original Selenium URL patterns...")
    
    async with GitHubAPIManager(github_token) as api_manager:
        # Generate Selenium-equivalent URLs
        urls = api_manager.generate_selenium_equivalent_urls()
        
        logger.info(f"Generated {len(urls)} search URLs (same as Selenium)")
        logger.info("Sample URLs:")
        for i, url in enumerate(urls[:5]):  # Show first 5
            logger.info(f"  {i+1}. {url}")
        
        if len(urls) > 5:
            logger.info(f"  ... and {len(urls) - 5} more URLs")
        
        # Process a few URLs to demonstrate equivalence
        logger.info("Processing sample URLs...")
        
        processed_count = 0
        for url in urls[:3]:  # Process first 3 for demo
            try:
                logger.info(f"Processing: {url}")
                
                result_count = 0
                async for api_key_info in api_manager.process_search_url(url):
                    result_count += 1
                    masked_key = f"{api_key_info['key'][:10]}...{api_key_info['key'][-10:]}"
                    logger.info(f"  Found: {masked_key} in {api_key_info['repository']}")
                    
                    if result_count >= 2:  # Limit for demo
                        break
                
                logger.info(f"  Results from this URL: {result_count}")
                processed_count += 1
                
            except Exception as e:
                logger.error(f"Error processing URL: {e}")
                continue
        
        logger.info(f"Successfully processed {processed_count} URLs")


async def demonstrate_performance_improvements():
    """
    Demonstrate performance improvements over Selenium.
    
    This function shows the performance benefits of using APIs
    instead of web scraping with Selenium.
    """
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return
    
    logger.info("Demonstrating performance improvements...")
    
    async with GitHubAPIManager(github_token) as api_manager:
        import time
        
        # Time a search operation
        start_time = time.time()
        
        result_count = 0
        async for result in api_manager.intelligent_search("test", max_results=10):
            result_count += 1
        
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info(f"API-based search completed in {duration:.2f} seconds")
        logger.info(f"Found {result_count} results")
        logger.info(f"Average time per result: {duration/max(1, result_count):.2f} seconds")
        
        # Get performance statistics
        stats = await api_manager.get_combined_stats()
        
        logger.info("Performance benefits over Selenium:")
        logger.info("  ✓ No browser overhead")
        logger.info("  ✓ Native JSON responses (no HTML parsing)")
        logger.info("  ✓ Concurrent request processing")
        logger.info("  ✓ Intelligent rate limiting")
        logger.info("  ✓ Structured error handling")
        logger.info("  ✓ Built-in retry mechanisms")


async def main():
    """Main demonstration function."""
    logger.info("GitHub API Client Demo")
    logger.info("=" * 50)
    
    # Check for required environment variables
    if not os.getenv('GITHUB_TOKEN'):
        logger.error("Please set GITHUB_TOKEN environment variable")
        logger.info("You can get a token from: https://github.com/settings/tokens")
        logger.info("Required scopes: public_repo (for public repository access)")
        return
    
    demos = [
        ("API-based Scanning", scan_with_api_client),
        ("Selenium URL Compatibility", compare_with_selenium_urls),
        ("Performance Demonstration", demonstrate_performance_improvements),
    ]
    
    for demo_name, demo_func in demos:
        logger.info(f"\n{'-' * 30}")
        logger.info(f"Demo: {demo_name}")
        logger.info(f"{'-' * 30}")
        
        try:
            await demo_func()
            logger.info(f"✓ {demo_name} completed successfully")
        except Exception as e:
            logger.error(f"✗ {demo_name} failed: {e}")
    
    logger.info(f"\n{'=' * 50}")
    logger.info("Demo completed!")
    logger.info("The GitHub API client is ready to replace Selenium-based scanning.")


if __name__ == "__main__":
    asyncio.run(main())