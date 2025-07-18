"""
GitHub API clients for code search and repository access.

This module provides async clients for GitHub REST and GraphQL APIs,
replacing Selenium-based scraping with native API calls for better
performance and reliability.
"""

import asyncio
import base64
import logging
from typing import AsyncIterator, List, Dict, Optional, Any
from datetime import datetime
from urllib.parse import quote

from .base_client import BaseAsyncClient
from ..async_core.interfaces import AsyncAPIClient, SearchResult
from ..async_core.exceptions import APIClientError, RateLimitError


class GitHubRESTClient(BaseAsyncClient, AsyncAPIClient):
    """
    Async GitHub REST API client for code search.
    
    Provides methods for searching code, accessing repositories, and
    retrieving file contents using GitHub's REST API v4.
    """
    
    def __init__(self, token: str, **kwargs) -> None:
        """
        Initialize GitHub REST client.
        
        Args:
            token: GitHub Personal Access Token
            **kwargs: Additional arguments for BaseAsyncClient
        """
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'ChatGPT-API-Scanner/2.0'
        }
        
        super().__init__(
            base_url='https://api.github.com',
            headers=headers,
            **kwargs
        )
        
        self.token = token
        self.search_delay = 2.0  # Ethical rate limiting
    
    async def search_code(
        self, 
        query: str, 
        language: Optional[str] = None,
        max_results: int = 1000
    ) -> AsyncIterator[SearchResult]:
        """
        Search for code using GitHub REST API.
        
        Args:
            query: Search query string
            language: Programming language filter
            max_results: Maximum number of results to return
            
        Yields:
            SearchResult: Individual search results
        """
        search_query = query
        if language:
            search_query += f" language:{language}"
        
        params = {
            'q': search_query,
            'sort': 'indexed',
            'order': 'desc',
            'per_page': min(100, max_results)  # GitHub API limit
        }
        
        page = 1
        total_results = 0
        
        while total_results < max_results:
            params['page'] = page
            
            try:
                # Ethical rate limiting
                await asyncio.sleep(self.search_delay)
                
                response = await self.get('/search/code', params=params)
                
                if 'items' not in response:
                    break
                
                items = response['items']
                if not items:
                    break
                
                for item in items:
                    if total_results >= max_results:
                        break
                    
                    yield SearchResult(
                        repository=item['repository']['full_name'],
                        file_path=item['path'],
                        content_snippet=item.get('text_matches', [{}])[0].get('fragment', ''),
                        line_number=0,  # REST API doesn't provide line numbers
                        sha=item['sha'],
                        url=item['html_url'],
                        timestamp=datetime.now()
                    )
                    
                    total_results += 1
                
                # Check if we've reached the end
                if len(items) < params['per_page']:
                    break
                
                page += 1
                
            except RateLimitError:
                self.logger.warning("Rate limited, waiting before retry")
                await asyncio.sleep(60)  # Wait 1 minute on rate limit
                continue
            except APIClientError as e:
                self.logger.error(f"API error during search: {e}")
                break
    
    async def get_file_content(
        self, 
        repo: str, 
        path: str, 
        ref: str = "main"
    ) -> str:
        """
        Get content of a specific file.
        
        Args:
            repo: Repository identifier (owner/repo)
            path: File path within repository
            ref: Git reference (branch, tag, commit)
            
        Returns:
            str: File content
        """
        endpoint = f'/repos/{repo}/contents/{quote(path)}'
        params = {'ref': ref}
        
        try:
            response = await self.get(endpoint, params=params)
            
            if response.get('encoding') == 'base64':
                content = base64.b64decode(response['content']).decode('utf-8')
                return content
            else:
                return response.get('content', '')
                
        except APIClientError as e:
            self.logger.error(f"Failed to get file content for {repo}/{path}: {e}")
            return ""
    
    async def batch_search(
        self, 
        queries: List[str]
    ) -> AsyncIterator[SearchResult]:
        """
        Perform multiple searches with proper rate limiting.
        
        Args:
            queries: List of search queries
            
        Yields:
            SearchResult: Results from all queries
        """
        for query in queries:
            async for result in self.search_code(query):
                yield result


class GitHubGraphQLClient(BaseAsyncClient):
    """
    Async GitHub GraphQL API client for advanced queries.
    
    Provides more efficient data retrieval using GraphQL queries
    with cursor-based pagination and optimized data fetching.
    """
    
    def __init__(self, token: str, **kwargs) -> None:
        """
        Initialize GitHub GraphQL client.
        
        Args:
            token: GitHub Personal Access Token
            **kwargs: Additional arguments for BaseAsyncClient
        """
        headers = {
            'Authorization': f'bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'ChatGPT-API-Scanner/2.0'
        }
        
        super().__init__(
            base_url='https://api.github.com/graphql',
            headers=headers,
            **kwargs
        )
        
        self.token = token
    
    async def execute_query(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query.
        
        Args:
            query: GraphQL query string
            variables: Query variables
            
        Returns:
            Dict[str, Any]: Query response data
        """
        payload = {'query': query}
        if variables:
            payload['variables'] = variables
        
        response = await self.post('', json_data=payload)
        
        if 'errors' in response:
            raise APIClientError(
                f"GraphQL errors: {response['errors']}",
                response_body=str(response)
            )
        
        return response.get('data', {})
    
    async def search_code_advanced(
        self,
        query: str,
        first: int = 100,
        after: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Advanced code search using GraphQL.
        
        Args:
            query: Search query
            first: Number of results to fetch
            after: Cursor for pagination
            
        Returns:
            Dict[str, Any]: Search results with pagination info
        """
        graphql_query = """
        query($query: String!, $first: Int!, $after: String) {
          search(query: $query, type: CODE, first: $first, after: $after) {
            codeCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              ... on CodeSearchResult {
                repository {
                  nameWithOwner
                  url
                }
                file {
                  name
                  path
                  url
                }
                textMatches {
                  fragment
                  highlights {
                    beginOffset
                    endOffset
                    text
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            'query': query,
            'first': first
        }
        
        if after:
            variables['after'] = after
        
        return await self.execute_query(graphql_query, variables)


class GitHubAPIManager:
    """
    Unified manager for GitHub REST and GraphQL clients.
    
    Coordinates between different GitHub API clients and provides
    intelligent client selection based on query type and rate limits.
    """
    
    def __init__(self, token: str) -> None:
        """
        Initialize GitHub API manager.
        
        Args:
            token: GitHub Personal Access Token
        """
        self.token = token
        self.rest_client: Optional[GitHubRESTClient] = None
        self.graphql_client: Optional[GitHubGraphQLClient] = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def initialize(self) -> None:
        """Initialize both REST and GraphQL clients."""
        self.rest_client = GitHubRESTClient(self.token)
        self.graphql_client = GitHubGraphQLClient(self.token)
        
        await self.rest_client.initialize()
        await self.graphql_client.initialize()
        
        self.logger.info("GitHub API manager initialized")
    
    async def close(self) -> None:
        """Close both clients."""
        if self.rest_client:
            await self.rest_client.close()
        if self.graphql_client:
            await self.graphql_client.close()
        
        self.logger.info("GitHub API manager closed")
    
    async def search_code(
        self, 
        query: str, 
        language: Optional[str] = None,
        max_results: int = 1000,
        use_graphql: bool = False
    ) -> AsyncIterator[SearchResult]:
        """
        Search code using the appropriate client.
        
        Args:
            query: Search query
            language: Programming language filter
            max_results: Maximum results to return
            use_graphql: Whether to use GraphQL client
            
        Yields:
            SearchResult: Search results
        """
        if use_graphql and self.graphql_client:
            # Use GraphQL for more advanced queries
            # Implementation would convert GraphQL results to SearchResult
            pass
        elif self.rest_client:
            async for result in self.rest_client.search_code(query, language, max_results):
                yield result
        else:
            raise APIClientError("No GitHub clients available")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False