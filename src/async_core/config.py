"""
Async configuration management extending existing configs.py.

This module provides async-aware configuration management with
validation, environment variable support, and dynamic updates
for the performance-optimized scanner.
"""

import os
import asyncio
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from pathlib import Path
import json
import logging

from .exceptions import ConfigurationError
from ..configs import REGEX_LIST, LANGUAGES, PATHS, KEYWORDS


@dataclass
class AsyncConfig:
    """Configuration for async components."""
    
    # GitHub API Configuration
    github_token: Optional[str] = None
    github_api_base_url: str = "https://api.github.com"
    github_graphql_url: str = "https://api.github.com/graphql"
    github_request_delay: float = 2.0  # Ethical rate limiting
    github_max_results_per_query: int = 1000
    
    # OpenAI API Configuration
    openai_api_base_url: str = "https://api.openai.com/v1"
    openai_max_concurrent_validations: int = 20
    openai_requests_per_minute: int = 50
    openai_requests_per_hour: int = 500
    openai_validation_cache_ttl: int = 3600  # 1 hour
    
    # Async Processing Configuration
    max_concurrent_searches: int = 10
    max_concurrent_validations: int = 20
    max_concurrent_file_reads: int = 50
    semaphore_github_api: int = 5
    semaphore_openai_api: int = 20
    
    # Cache Configuration
    cache_sqlite_path: str = "async_cache.db"
    cache_redis_url: Optional[str] = None
    cache_max_memory_entries: int = 10000
    cache_default_ttl: int = 3600
    
    # Database Configuration
    database_path: str = "github.db"
    database_timeout: int = 30
    database_max_connections: int = 10
    database_batch_size: int = 1000
    
    # HTTP Client Configuration
    http_timeout: int = 30
    http_max_connections: int = 100
    http_max_connections_per_host: int = 30
    http_retry_attempts: int = 3
    http_retry_delay: float = 1.0
    
    # Pattern Matching Configuration
    pattern_chunk_size: int = 10000
    pattern_confidence_threshold: float = 0.7
    pattern_context_window: int = 200
    false_positive_filter_enabled: bool = True
    
    # Monitoring Configuration
    metrics_enabled: bool = True
    metrics_max_points: int = 10000
    metrics_cleanup_interval: int = 300  # 5 minutes
    performance_monitoring_enabled: bool = True
    
    # Security Configuration
    encrypt_database: bool = True
    encrypt_cache: bool = True
    log_api_keys: bool = False  # Never log actual API keys
    mask_sensitive_data: bool = True
    
    # Legacy Configuration (from original configs.py)
    regex_patterns: List = field(default_factory=lambda: REGEX_LIST)
    supported_languages: List[str] = field(default_factory=lambda: LANGUAGES)
    search_paths: List[str] = field(default_factory=lambda: PATHS)
    keywords: List[str] = field(default_factory=lambda: KEYWORDS)


class AsyncConfigManager:
    """
    Async configuration manager with validation and environment support.
    
    Manages configuration for async components with support for
    environment variables, validation, and dynamic updates.
    """
    
    def __init__(self, config_file: Optional[str] = None) -> None:
        """
        Initialize async config manager.
        
        Args:
            config_file: Optional path to configuration file
        """
        self.config_file = config_file
        self.config = AsyncConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._watchers: List[asyncio.Task] = []
    
    async def load_config(self) -> AsyncConfig:
        """
        Load configuration from file and environment variables.
        
        Returns:
            AsyncConfig: Loaded configuration
        """
        # Load from file if specified
        if self.config_file and Path(self.config_file).exists():
            await self._load_from_file()
        
        # Override with environment variables
        await self._load_from_environment()
        
        # Validate configuration
        await self._validate_config()
        
        self.logger.info("Configuration loaded successfully")
        return self.config
    
    async def _load_from_file(self) -> None:
        """Load configuration from JSON file."""
        try:
            with open(self.config_file, 'r') as f:
                config_data = json.load(f)
            
            # Update config with file data
            for key, value in config_data.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                else:
                    self.logger.warning(f"Unknown config key: {key}")
            
            self.logger.debug(f"Configuration loaded from {self.config_file}")
            
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load config from {self.config_file}: {e}",
                config_key="config_file",
                config_value=self.config_file
            )
    
    async def _load_from_environment(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            'GITHUB_TOKEN': 'github_token',
            'GITHUB_API_DELAY': ('github_request_delay', float),
            'OPENAI_MAX_CONCURRENT': ('openai_max_concurrent_validations', int),
            'OPENAI_REQUESTS_PER_MINUTE': ('openai_requests_per_minute', int),
            'CACHE_REDIS_URL': 'cache_redis_url',
            'DATABASE_PATH': 'database_path',
            'HTTP_TIMEOUT': ('http_timeout', int),
            'METRICS_ENABLED': ('metrics_enabled', bool),
            'ENCRYPT_DATABASE': ('encrypt_database', bool),
        }
        
        for env_var, config_mapping in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                if isinstance(config_mapping, tuple):
                    config_key, value_type = config_mapping
                    try:
                        if value_type == bool:
                            value = env_value.lower() in ('true', '1', 'yes', 'on')
                        else:
                            value = value_type(env_value)
                        setattr(self.config, config_key, value)
                    except ValueError as e:
                        self.logger.warning(
                            f"Invalid value for {env_var}: {env_value} ({e})"
                        )
                else:
                    setattr(self.config, config_mapping, env_value)
        
        self.logger.debug("Environment variables loaded")
    
    async def _validate_config(self) -> None:
        """Validate configuration values."""
        errors = []
        
        # Validate required fields
        if not self.config.github_token:
            errors.append("GitHub token is required (set GITHUB_TOKEN environment variable)")
        
        # Validate numeric ranges
        if self.config.github_request_delay < 0.1:
            errors.append("GitHub request delay must be at least 0.1 seconds")
        
        if self.config.openai_max_concurrent_validations < 1:
            errors.append("OpenAI max concurrent validations must be at least 1")
        
        if self.config.openai_requests_per_minute < 1:
            errors.append("OpenAI requests per minute must be at least 1")
        
        # Validate file paths
        database_dir = Path(self.config.database_path).parent
        if not database_dir.exists():
            try:
                database_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create database directory: {e}")
        
        cache_dir = Path(self.config.cache_sqlite_path).parent
        if not cache_dir.exists():
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create cache directory: {e}")
        
        # Validate URLs
        if not self.config.github_api_base_url.startswith('https://'):
            errors.append("GitHub API base URL must use HTTPS")
        
        if not self.config.openai_api_base_url.startswith('https://'):
            errors.append("OpenAI API base URL must use HTTPS")
        
        if errors:
            raise ConfigurationError(
                f"Configuration validation failed: {'; '.join(errors)}"
            )
        
        self.logger.debug("Configuration validation passed")
    
    async def save_config(self, file_path: Optional[str] = None) -> None:
        """
        Save current configuration to file.
        
        Args:
            file_path: Optional path to save to (defaults to config_file)
        """
        save_path = file_path or self.config_file
        if not save_path:
            raise ConfigurationError("No file path specified for saving config")
        
        # Convert config to dict, excluding non-serializable fields
        config_dict = {}
        for key, value in self.config.__dict__.items():
            if not key.startswith('_') and isinstance(value, (str, int, float, bool, list, dict, type(None))):
                config_dict[key] = value
        
        try:
            with open(save_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            self.logger.info(f"Configuration saved to {save_path}")
            
        except Exception as e:
            raise ConfigurationError(
                f"Failed to save config to {save_path}: {e}",
                config_key="save_path",
                config_value=save_path
            )
    
    async def update_config(self, updates: Dict[str, Any]) -> None:
        """
        Update configuration with new values.
        
        Args:
            updates: Dictionary of configuration updates
        """
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                self.logger.debug(f"Updated config: {key} = {value}")
            else:
                self.logger.warning(f"Unknown config key: {key}")
        
        # Re-validate after updates
        await self._validate_config()
    
    async def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Any: Configuration value
        """
        return getattr(self.config, key, default)
    
    async def watch_config_file(self, callback: Optional[callable] = None) -> None:
        """
        Watch configuration file for changes.
        
        Args:
            callback: Optional callback function to call on changes
        """
        if not self.config_file or not Path(self.config_file).exists():
            return
        
        async def file_watcher():
            last_modified = Path(self.config_file).stat().st_mtime
            
            while True:
                try:
                    await asyncio.sleep(1)  # Check every second
                    
                    current_modified = Path(self.config_file).stat().st_mtime
                    if current_modified > last_modified:
                        self.logger.info("Configuration file changed, reloading...")
                        await self.load_config()
                        last_modified = current_modified
                        
                        if callback:
                            await callback(self.config)
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"Error watching config file: {e}")
                    await asyncio.sleep(5)  # Wait before retrying
        
        watcher_task = asyncio.create_task(file_watcher())
        self._watchers.append(watcher_task)
        self.logger.info(f"Started watching config file: {self.config_file}")
    
    async def stop_watchers(self) -> None:
        """Stop all configuration file watchers."""
        for watcher in self._watchers:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
        
        self._watchers.clear()
        self.logger.info("Stopped all config watchers")


# Global config manager instance
config_manager = AsyncConfigManager()


async def get_config() -> AsyncConfig:
    """
    Get the global configuration instance.
    
    Returns:
        AsyncConfig: Global configuration
    """
    if not hasattr(config_manager, '_loaded'):
        await config_manager.load_config()
        config_manager._loaded = True
    
    return config_manager.config