#!/usr/bin/env python3
"""
Example of how GitHubAPIManager replaces Selenium-based scanning.

This demonstrates the integration of the new API-based scanner with the existing
database and validation infrastructure.
"""

import asyncio
import logging
import os
from typing import List, Dict, Any

from .api_clients.github_client import GitHubAPIManager
from .manager import DatabaseManager
from .utils import check_key
from .configs import KEYWORDS, LANGUAGES

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AsyncAPIKeyLeakageScanner:
    """
    Async version of APIKeyLeakageScanner using GitHubAPIManager.
    
    This class demonstrates how to replace the Selenium-based scanner
    with the new API-based approach while maintaining compatibility
    with existing database and validation infrastructure.
    """
    
    def __init__(self, db_file: str, github_token: str, keywords: List[str] = None, languages: List[str] = None):
        """
        Initialize the async scanner.
        
        Args:
            db_file: Database file path
            github_token: GitHub Personal Access Token
            keywords: Keywords to search (for future use)
            languages: Languages to filter
        """
        self.db_file = db_file
        self.github_token = github_token
        self.keywords = keywords or KEYWORDS.copy()
        self.languages = languages or LANGUAGES.copy()
        
        self.dbmgr = DatabaseManager(self.db_file)
        self.github_manager: GitHubAPIManager = None
        
        logger.info(f"📂 Initialized async scanner with database: {self.db_file}")
    
    async def initialize(self) -> None:
        """Initialize the GitHub API manager."""
        self.github_manager = GitHubAPIManager(self.github_token)
        await self.github_manager.initialize()
        logger.info("🚀 GitHub API manager initialized")
    
    async def close(self) -> None:
        """Close the GitHub API manager."""
        if self.github_manager:
            await self.github_manager.close()
            logger.info("🔒 GitHub API manager closed")
    
    async def scan_repositories(self) -> None:
        """
        Scan repositories for API keys using the new API-based approach.
        
        This method replaces the original Selenium-based scanning while
        maintaining the same database storage and validation patterns.
        """
        if not self.github_manager:
            raise ValueError("GitHub manager not initialized")
        
        logger.info("🔍 Starting API-based repository scan...")
        
        found_keys = []
        processed_count = 0
        
        try:
            # Use the GitHubAPIManager to replace Selenium functionality
            async for api_key_info in self.github_manager.replace_selenium_scanner(
                keywords=self.keywords,
                languages=self.languages
            ):
                processed_count += 1
                
                # Extract the API key from the result
                api_key = api_key_info.get('key')
                if not api_key:
                    continue
                
                # Check if we've already processed this key
                with self.dbmgr as mgr:
                    if mgr.key_exists(api_key):
                        logger.debug(f"🔑 Skipping existing key: {api_key[:10]}...")
                        continue
                
                found_keys.append(api_key)
                
                # Log progress
                if processed_count % 10 == 0:
                    logger.info(f"📊 Processed {processed_count} results, found {len(found_keys)} new keys")
                
                # Process in batches to avoid memory issues
                if len(found_keys) >= 50:
                    await self._validate_and_store_keys(found_keys)
                    found_keys = []
        
        except Exception as e:
            logger.error(f"❌ Error during repository scan: {e}")
            raise
        
        # Process remaining keys
        if found_keys:
            await self._validate_and_store_keys(found_keys)
        
        logger.info(f"✅ Repository scan completed. Processed {processed_count} results.")
    
    async def _validate_and_store_keys(self, api_keys: List[str]) -> None:
        """
        Validate and store API keys (same logic as original implementation).
        
        Args:
            api_keys: List of API keys to validate and store
        """
        logger.info(f"🔐 Validating {len(api_keys)} API keys...")
        
        # Filter out keys that already exist in database
        with self.dbmgr as mgr:
            unique_keys = [key for key in api_keys if not mgr.key_exists(key)]
        
        if not unique_keys:
            logger.info("ℹ️  All keys already exist in database")
            return
        
        # Validate keys (using existing validation logic)
        validation_tasks = []
        for key in unique_keys:
            # Create async task for validation (would need to make check_key async)
            # For now, we'll use the synchronous version
            validation_tasks.append(self._validate_key_async(key))
        
        # Wait for all validations to complete
        results = await asyncio.gather(*validation_tasks, return_exceptions=True)
        
        # Store results in database
        with self.dbmgr as mgr:
            for key, result in zip(unique_keys, results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Validation failed for key {key[:10]}...: {result}")
                    mgr.insert(key, "validation_error")
                else:
                    mgr.insert(key, result)
                    logger.debug(f"✅ Stored key {key[:10]}... with status: {result}")
        
        logger.info(f"💾 Stored {len(unique_keys)} validated keys")
    
    async def _validate_key_async(self, api_key: str) -> str:
        """
        Async wrapper for key validation.
        
        Args:
            api_key: API key to validate
            
        Returns:
            str: Validation result status
        """
        # Run the synchronous validation in a thread pool
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, check_key, api_key)
            return result
        except Exception as e:
            logger.error(f"❌ Key validation error: {e}")
            return "validation_error"
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get scanning statistics.
        
        Returns:
            Dict[str, Any]: Statistics about the scanning process
        """
        stats = {}
        
        if self.github_manager:
            stats['github_api'] = await self.github_manager.get_combined_stats()
        
        # Database statistics
        with self.dbmgr as mgr:
            stats['database'] = {
                'total_keys': len(mgr.all_keys()),
                'insufficient_quota_keys': len(mgr.all_iq_keys())
            }
        
        return stats
    
    async def update_existing_keys(self) -> None:
        """Update existing keys in database (same as original implementation)."""
        logger.info("🔄 Updating existing keys...")
        
        with self.dbmgr as mgr:
            keys = mgr.all_keys()
            
        update_tasks = []
        for key_tuple in keys:
            key = key_tuple[0]
            update_tasks.append(self._validate_key_async(key))
        
        if update_tasks:
            results = await asyncio.gather(*update_tasks, return_exceptions=True)
            
            with self.dbmgr as mgr:
                for key_tuple, result in zip(keys, results):
                    key = key_tuple[0]
                    mgr.delete(key)
                    
                    if isinstance(result, Exception):
                        mgr.insert(key, "validation_error")
                    else:
                        mgr.insert(key, result)
        
        logger.info(f"✅ Updated {len(keys)} existing keys")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False


async def main_async_example():
    """
    Example of how to use the new async scanner.
    
    This demonstrates the complete replacement of Selenium-based scanning
    with API-based scanning using GitHubAPIManager.
    """
    # Configuration
    db_file = "github_async.db"
    github_token = os.getenv('GITHUB_TOKEN', 'your_github_token_here')
    
    logger.info("🚀 Starting Async API Key Scanner Example")
    
    try:
        # Use the new async scanner
        async with AsyncAPIKeyLeakageScanner(db_file, github_token) as scanner:
            
            # Get initial statistics
            stats = await scanner.get_statistics()
            logger.info(f"📊 Initial stats: {stats}")
            
            # Perform the scan (replaces Selenium-based scanning)
            await scanner.scan_repositories()
            
            # Update existing keys
            await scanner.update_existing_keys()
            
            # Get final statistics
            final_stats = await scanner.get_statistics()
            logger.info(f"📊 Final stats: {final_stats}")
            
            # Show results
            with scanner.dbmgr as mgr:
                available_keys = mgr.all_keys()
                logger.info(f"🔑 Found {len(available_keys)} available API keys")
                
                for key_tuple in available_keys[:5]:  # Show first 5
                    key = key_tuple[0]
                    logger.info(f"   Key: {key[:10]}...{key[-10:]}")
    
    except Exception as e:
        logger.error(f"❌ Scanner failed: {e}")
        raise
    
    logger.info("✅ Async API Key Scanner completed successfully")


if __name__ == "__main__":
    # This would be the new main function using API-based scanning
    asyncio.run(main_async_example())