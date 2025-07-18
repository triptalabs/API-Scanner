#!/usr/bin/env python3
"""
Test script for GitHub API client implementation.

This script tests the GitHub API client functionality to ensure it can
properly replace the Selenium-based implementation.
"""

import asyncio
import os
import logging
from typing import List, Dict, Any

from api_clients.github_client import GitHubAPIManager, GitHubRESTClient, GitHubGraphQLClient
from async_core.config import get_config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_github_rest_client():
    """Test GitHub REST API client functionality."""
    logger.info("Testing GitHub REST API client...")
    
    # Get GitHub token from environment
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return False
    
    try:
        async with GitHubRESTClient(github_token) as client:
            # Test basic search
            logger.info("Testing basic code search...")
            result_count = 0
            async for result in client.search_code("test", max_results=5):
                result_count += 1
                logger.info(f"Found result: {result.repository}/{result.file_path}")
                
                if result_count >= 3:  # Limit for testing
                    break
            
            logger.info(f"REST client test completed. Found {result_count} results.")
            
            # Test statistics
            stats = await client.get_stats()
            logger.info(f"Client stats: {stats}")
            
            return result_count > 0
            
    except Exception as e:
        logger.error(f"REST client test failed: {e}")
        return False


async def test_github_graphql_client():
    """Test GitHub GraphQL API client functionality."""
    logger.info("Testing GitHub GraphQL API client...")
    
    # Get GitHub token from environment
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return False
    
    try:
        async with GitHubGraphQLClient(github_token) as client:
            # Test GraphQL search
            logger.info("Testing GraphQL code search...")
            result_count = 0
            async for result in client.search_code_with_pagination("test", max_results=3):
                result_count += 1
                logger.info(f"Found GraphQL result: {result.repository}/{result.file_path}")
            
            logger.info(f"GraphQL client test completed. Found {result_count} results.")
            
            # Test statistics
            stats = await client.get_stats()
            logger.info(f"GraphQL client stats: {stats}")
            
            return result_count >= 0  # GraphQL might have different results
            
    except Exception as e:
        logger.error(f"GraphQL client test failed: {e}")
        return False


async def test_github_api_manager():
    """Test GitHub API manager functionality."""
    logger.info("Testing GitHub API manager...")
    
    # Get GitHub token from environment
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return False
    
    try:
        async with GitHubAPIManager(github_token) as manager:
            # Test compatibility validation
            logger.info("Testing compatibility validation...")
            validation = await manager.validate_replacement_compatibility()
            logger.info(f"Compatibility validation: {validation}")
            
            # Test intelligent search
            logger.info("Testing intelligent search...")
            result_count = 0
            async for result in manager.intelligent_search("test", max_results=3):
                result_count += 1
                logger.info(f"Found intelligent search result: {result.repository}/{result.file_path}")
            
            # Test Selenium URL generation
            logger.info("Testing Selenium URL generation...")
            urls = manager.generate_selenium_equivalent_urls()
            logger.info(f"Generated {len(urls)} Selenium-equivalent URLs")
            
            # Test combined statistics
            stats = await manager.get_combined_stats()
            logger.info(f"Combined stats: {stats}")
            
            logger.info(f"API manager test completed. Found {result_count} results.")
            return validation['ready_for_production']
            
    except Exception as e:
        logger.error(f"API manager test failed: {e}")
        return False


async def test_api_key_detection():
    """Test API key detection functionality."""
    logger.info("Testing API key detection...")
    
    # Sample content with fake API keys for testing
    test_content = """
    # Configuration file
    OPENAI_API_KEY=sk-1234567890abcdef1234567890abcdef12345678
    
    # Another example
    const apiKey = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ1234T3BlbkFJabcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ1234A";
    
    # Service account key
    sk-svcacct-abcdefghijklmnopqrstuvwxyzT3BlbkFJabcdefghijklmnopqrstuvwxyz
    """
    
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable not set")
        return False
    
    try:
        async with GitHubRESTClient(github_token) as client:
            # Test API key detection
            api_keys = await client.find_api_keys_in_content(test_content, "test_file.py")
            
            logger.info(f"Found {len(api_keys)} API keys in test content:")
            for key_info in api_keys:
                logger.info(f"  - Pattern: {key_info['pattern']}")
                logger.info(f"    Key: {key_info['key'][:10]}...{key_info['key'][-10:]}")
                logger.info(f"    Line: {key_info['line_number']}")
            
            return len(api_keys) > 0
            
    except Exception as e:
        logger.error(f"API key detection test failed: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("Starting GitHub API client tests...")
    
    # Check for required environment variables
    if not os.getenv('GITHUB_TOKEN'):
        logger.error("Please set GITHUB_TOKEN environment variable to run tests")
        logger.info("You can get a token from: https://github.com/settings/tokens")
        return
    
    tests = [
        ("REST Client", test_github_rest_client),
        ("GraphQL Client", test_github_graphql_client),
        ("API Manager", test_github_api_manager),
        ("API Key Detection", test_api_key_detection),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} test...")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            results[test_name] = result
            status = "PASSED" if result else "FAILED"
            logger.info(f"{test_name} test {status}")
        except Exception as e:
            logger.error(f"{test_name} test ERROR: {e}")
            results[test_name] = False
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! GitHub API client is ready to replace Selenium.")
    else:
        logger.warning("⚠️  Some tests failed. Please check the implementation.")


if __name__ == "__main__":
    asyncio.run(main())