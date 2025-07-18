"""
Base client for API interactions.

This module provides the foundational async HTTP client functionality
that other API clients inherit from, ensuring consistent patterns for
authentication, error handling, and rate limiting.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta

from ..async_core.base import AsyncContextManager
from ..async_core.exceptions import APIClientError, RateLimitError


class BaseAsyncClient(AsyncContextManager):
    """
    Base async HTTP client for API interactions.
    
    Provides common functionality for making HTTP requests with proper
    error handling, rate limiting, and connection management.
    """
    
    def __init__(
        self, 
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        max_connections: int = 100,
        max_connections_per_host: int = 30
    ) -> None:
        """
        Initialize base async client.
        
        Args:
            base_url: Base URL for API requests
            headers: Default headers for requests
            timeout: Request timeout in seconds
            max_connections: Maximum total connections
            max_connections_per_host: Maximum connections per host
        """
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.default_headers = headers or {}
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
        # Connection pool configuration
        self.connector = aiohttp.TCPConnector(
            limit=max_connections,
            limit_per_host=max_connections_per_host,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def _async_init(self) -> None:
        """Initialize the HTTP session."""
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=self.timeout,
            headers=self.default_headers
        )
        self.logger.debug("HTTP session initialized")
    
    async def _async_close(self) -> None:
        """Close the HTTP session and connector."""
        if self.session:
            await self.session.close()
            self.session = None
        
        if self.connector:
            await self.connector.close()
        
        self.logger.debug("HTTP session closed")
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None
    ) -> aiohttp.ClientResponse:
        """
        Make an HTTP request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to base_url)
            headers: Additional headers for this request
            params: Query parameters
            json_data: JSON data for request body
            data: Raw data for request body
            
        Returns:
            aiohttp.ClientResponse: The response object
            
        Raises:
            APIClientError: If the request fails
            RateLimitError: If rate limited
        """
        if not self.session:
            raise APIClientError("Client not initialized. Use async context manager.")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)
        
        try:
            self.logger.debug(f"Making {method} request to {url}")
            
            async with self.session.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                json=json_data,
                data=data
            ) as response:
                
                # Handle rate limiting
                if response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    raise RateLimitError(
                        f"Rate limited by {self.__class__.__name__}",
                        retry_after=retry_after,
                        service=self.__class__.__name__
                    )
                
                # Handle other HTTP errors
                if response.status >= 400:
                    error_body = await response.text()
                    raise APIClientError(
                        f"HTTP {response.status} error from {url}",
                        status_code=response.status,
                        response_body=error_body,
                        endpoint=endpoint
                    )
                
                self.logger.debug(f"Request successful: {response.status}")
                return response
                
        except aiohttp.ClientError as e:
            raise APIClientError(f"Request failed: {str(e)}", endpoint=endpoint)
    
    async def get(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a GET request and return JSON response.
        
        Args:
            endpoint: API endpoint
            headers: Additional headers
            params: Query parameters
            
        Returns:
            Dict[str, Any]: JSON response data
        """
        response = await self._make_request('GET', endpoint, headers, params)
        return await response.json()
    
    async def post(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """
        Make a POST request and return JSON response.
        
        Args:
            endpoint: API endpoint
            headers: Additional headers
            params: Query parameters
            json_data: JSON data for request body
            data: Raw data for request body
            
        Returns:
            Dict[str, Any]: JSON response data
        """
        response = await self._make_request(
            'POST', endpoint, headers, params, json_data, data
        )
        return await response.json()
    
    async def get_text(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Make a GET request and return text response.
        
        Args:
            endpoint: API endpoint
            headers: Additional headers
            params: Query parameters
            
        Returns:
            str: Response text
        """
        response = await self._make_request('GET', endpoint, headers, params)
        return await response.text()