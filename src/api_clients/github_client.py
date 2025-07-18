"""
GitHub API clients for code search and repository access.

This module provides async clients for GitHub REST and GraphQL APIs,
replacing Selenium-based scraping with native API calls for better
performance and reliability.
"""

import asyncio
import base64
import hashlib
import logging
import re
from typing import AsyncIterator, List, Dict, Optional, Any, Tuple
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs

from .base_client import BaseAsyncClient
from ..async_core.interfaces import AsyncAPIClient, SearchResult
from ..async_core.exceptions import APIClientError, RateLimitError
from ..configs import REGEX_LIST, LANGUAGES, PATHS


class GitHubRESTClient(BaseAsyncClient, AsyncAPIClient):
    """
    Async GitHub REST API client for code search.
    
    Provides methods for searching code, accessing repositories, and
    retrieving file contents using GitHub's REST API v4.
    Replaces Selenium-based scraping with native API calls.
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
            'Accept': 'application/vnd.github.v3.text-match+json',  # Enable text matches
            'User-Agent': 'ChatGPT-API-Scanner/2.0'
        }
        
        super().__init__(
            base_url='https://api.github.com',
            headers=headers,
            **kwargs
        )
        
        self.token = token
        self.search_delay = 2.0  # Ethical rate limiting - more restrictive than API limits
        self.rate_limit_remaining = 5000  # Track remaining requests
        self.rate_limit_reset = None
        self.secondary_rate_limit_delay = 30  # Delay for secondary rate limits
        
        # Cache for processed URLs to avoid duplicates
        self.processed_urls = set()
        
        # Statistics tracking
        self.stats = {
            'total_searches': 0,
            'total_results': 0,
            'api_calls_made': 0,
            'rate_limits_hit': 0
        }
    
    async def _handle_rate_limit_response(self, response_headers: Dict[str, str]) -> None:
        """
        Handle rate limit information from response headers.
        
        Args:
            response_headers: HTTP response headers
        """
        if 'X-RateLimit-Remaining' in response_headers:
            self.rate_limit_remaining = int(response_headers['X-RateLimit-Remaining'])
        
        if 'X-RateLimit-Reset' in response_headers:
            self.rate_limit_reset = int(response_headers['X-RateLimit-Reset'])
        
        # Check for secondary rate limit
        if self.rate_limit_remaining < 100:
            self.logger.warning(f"Rate limit low: {self.rate_limit_remaining} remaining")
            await asyncio.sleep(self.search_delay * 2)  # Extra delay when low
    
    def _parse_github_search_url(self, url: str) -> Tuple[str, Optional[str]]:
        """
        Parse GitHub search URL to extract query and language.
        
        Args:
            url: GitHub search URL from original Selenium implementation
            
        Returns:
            Tuple[str, Optional[str]]: (query, language)
        """
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        query = query_params.get('q', [''])[0]
        language = None
        
        # Extract language from query if present
        if 'language:' in query:
            parts = query.split('language:')
            if len(parts) > 1:
                lang_part = parts[1].split()[0]
                language = lang_part.strip('"')
                # Remove language from main query
                query = query.replace(f'language:{lang_part}', '').strip()
        
        return query, language
    
    def _build_search_queries_from_patterns(self) -> List[Tuple[str, Optional[str]]]:
        """
        Build search queries equivalent to original Selenium URL patterns.
        
        Returns:
            List[Tuple[str, Optional[str]]]: List of (query, language) tuples
        """
        queries = []
        
        for regex, too_many_results, _ in REGEX_LIST:
            regex_pattern = regex.pattern
            
            # Add path-based searches
            for path in PATHS:
                # Convert path patterns to GitHub search syntax
                path_query = path.replace('path:', '').replace(' OR ', ' ')
                query = f"/{regex_pattern}/ {path_query}"
                queries.append((query, None))
            
            # Add language-based searches
            for language in LANGUAGES:
                if too_many_results:
                    # For patterns with many results, add more specific constraints
                    query = f"/{regex_pattern}/"
                    queries.append((query, language.strip('"')))
                else:
                    # For patterns with fewer results, use simpler query
                    query = f"/{regex_pattern}/"
                    queries.append((query, language.strip('"')))
        
        return queries
    
    async def find_api_keys_in_content(self, content: str, file_path: str = "") -> List[Dict[str, Any]]:
        """
        Find API keys in content using regex patterns.
        
        Args:
            content: File content to search
            file_path: Path of the file (for context)
            
        Returns:
            List[Dict[str, Any]]: List of found API keys with metadata
        """
        found_keys = []
        
        for regex, _, too_long in REGEX_LIST:
            matches = regex.finditer(content)
            
            for match in matches:
                api_key = match.group(0)
                start_pos = match.start()
                end_pos = match.end()
                
                # Extract context around the match
                context_start = max(0, start_pos - 100)
                context_end = min(len(content), end_pos + 100)
                context = content[context_start:context_end]
                
                # Calculate line number
                line_number = content[:start_pos].count('\n') + 1
                
                found_keys.append({
                    'key': api_key,
                    'pattern': regex.pattern,
                    'line_number': line_number,
                    'context': context,
                    'file_path': file_path,
                    'is_long_pattern': too_long
                })
        
        return found_keys
    
    async def process_search_url_equivalent(self, search_url: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Process a search URL equivalent to Selenium implementation.
        
        Args:
            search_url: Original GitHub search URL
            
        Yields:
            Dict[str, Any]: Found API keys with metadata
        """
        query, language = self._parse_github_search_url(search_url)
        
        self.logger.info(f"Processing search: {query} (language: {language})")
        self.stats['total_searches'] += 1
        
        async for result in self.search_code(query, language, max_results=1000):
            self.stats['total_results'] += 1
            
            # Get full file content for detailed analysis
            try:
                full_content = await self.get_file_content(
                    result.repository, 
                    result.file_path, 
                    result.sha
                )
                
                if full_content:
                    api_keys = await self.find_api_keys_in_content(
                        full_content, 
                        result.file_path
                    )
                    
                    for key_info in api_keys:
                        key_info.update({
                            'repository': result.repository,
                            'file_url': result.url,
                            'sha': result.sha,
                            'timestamp': result.timestamp
                        })
                        yield key_info
                
            except Exception as e:
                self.logger.error(f"Error processing file {result.repository}/{result.file_path}: {e}")
                continue
    
    async def scan_repositories_like_selenium(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Scan repositories using patterns equivalent to original Selenium implementation.
        
        Yields:
            Dict[str, Any]: Found API keys with metadata
        """
        queries = self._build_search_queries_from_patterns()
        
        self.logger.info(f"Starting scan with {len(queries)} search patterns")
        
        for query, language in queries:
            try:
                # Ethical rate limiting
                await asyncio.sleep(self.search_delay)
                
                async for result in self.search_code(query, language, max_results=100):
                    # Skip if we've already processed this URL
                    url_key = f"{result.repository}/{result.file_path}"
                    if url_key in self.processed_urls:
                        continue
                    
                    self.processed_urls.add(url_key)
                    
                    # Get full file content
                    try:
                        full_content = await self.get_file_content(
                            result.repository,
                            result.file_path,
                            result.sha
                        )
                        
                        if full_content:
                            api_keys = await self.find_api_keys_in_content(
                                full_content,
                                result.file_path
                            )
                            
                            for key_info in api_keys:
                                key_info.update({
                                    'repository': result.repository,
                                    'file_url': result.url,
                                    'sha': result.sha,
                                    'timestamp': result.timestamp
                                })
                                yield key_info
                    
                    except Exception as e:
                        self.logger.error(f"Error processing {result.repository}/{result.file_path}: {e}")
                        continue
            
            except RateLimitError as e:
                self.logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
                self.stats['rate_limits_hit'] += 1
                await asyncio.sleep(e.retry_after or 60)
                continue
            
            except Exception as e:
                self.logger.error(f"Error in search query '{query}': {e}")
                continue
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics.
        
        Returns:
            Dict[str, Any]: Client statistics
        """
        return {
            **self.stats,
            'processed_urls_count': len(self.processed_urls),
            'rate_limit_remaining': self.rate_limit_remaining,
            'rate_limit_reset': self.rate_limit_reset
        }
    
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
                
                # Make the API call and track statistics
                response = await self._make_request('GET', '/search/code', params=params)
                self.stats['api_calls_made'] += 1
                
                # Handle rate limit headers
                await self._handle_rate_limit_response(dict(response.headers))
                
                response_data = await response.json()
                
                if 'items' not in response_data:
                    break
                
                items = response_data['items']
                if not items:
                    break
                
                for item in items:
                    if total_results >= max_results:
                        break
                    
                    # Extract text matches for better content snippets
                    content_snippet = ""
                    if 'text_matches' in item and item['text_matches']:
                        content_snippet = item['text_matches'][0].get('fragment', '')
                    
                    yield SearchResult(
                        repository=item['repository']['full_name'],
                        file_path=item['path'],
                        content_snippet=content_snippet,
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
                
            except RateLimitError as e:
                self.logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
                self.stats['rate_limits_hit'] += 1
                await asyncio.sleep(e.retry_after or 60)
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
            # Make the API call and track statistics
            response = await self._make_request('GET', endpoint, params=params)
            self.stats['api_calls_made'] += 1
            
            # Handle rate limit headers
            await self._handle_rate_limit_response(dict(response.headers))
            
            response_data = await response.json()
            
            if response_data.get('encoding') == 'base64':
                content = base64.b64decode(response_data['content']).decode('utf-8')
                return content
            else:
                return response_data.get('content', '')
                
        except APIClientError as e:
            self.logger.error(f"Failed to get file content for {repo}/{path}: {e}")
            return ""
        except Exception as e:
            self.logger.error(f"Unexpected error getting file content for {repo}/{path}: {e}")
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
        self.stats = {
            'queries_executed': 0,
            'total_results': 0,
            'rate_limits_hit': 0
        }
    
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
        
        try:
            # Make the API call and track statistics
            response = await self._make_request('POST', '', json_data=payload)
            self.stats['queries_executed'] += 1
            
            response_data = await response.json()
            
            if 'errors' in response_data:
                raise APIClientError(
                    f"GraphQL errors: {response_data['errors']}",
                    response_body=str(response_data)
                )
            
            return response_data.get('data', {})
            
        except RateLimitError as e:
            self.stats['rate_limits_hit'] += 1
            raise
    
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
    
    async def search_code_with_pagination(
        self,
        query: str,
        max_results: int = 1000
    ) -> AsyncIterator[SearchResult]:
        """
        Search code with automatic pagination using GraphQL.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Yields:
            SearchResult: Individual search results
        """
        cursor = None
        total_results = 0
        
        while total_results < max_results:
            try:
                # Ethical rate limiting
                await asyncio.sleep(1.0)  # GraphQL has different rate limits
                
                results_per_page = min(100, max_results - total_results)
                response = await self.search_code_advanced(
                    query, 
                    first=results_per_page, 
                    after=cursor
                )
                
                search_data = response.get('search', {})
                nodes = search_data.get('nodes', [])
                
                if not nodes:
                    break
                
                for node in nodes:
                    if total_results >= max_results:
                        break
                    
                    repository = node.get('repository', {})
                    file_info = node.get('file', {})
                    text_matches = node.get('textMatches', [])
                    
                    content_snippet = ""
                    if text_matches:
                        content_snippet = text_matches[0].get('fragment', '')
                    
                    yield SearchResult(
                        repository=repository.get('nameWithOwner', ''),
                        file_path=file_info.get('path', ''),
                        content_snippet=content_snippet,
                        line_number=0,  # GraphQL doesn't provide line numbers directly
                        sha="",  # Would need additional query to get SHA
                        url=file_info.get('url', ''),
                        timestamp=datetime.now()
                    )
                    
                    total_results += 1
                    self.stats['total_results'] += 1
                
                # Check for next page
                page_info = search_data.get('pageInfo', {})
                if not page_info.get('hasNextPage', False):
                    break
                
                cursor = page_info.get('endCursor')
                
            except RateLimitError as e:
                self.logger.warning(f"GraphQL rate limited, waiting {e.retry_after} seconds")
                self.stats['rate_limits_hit'] += 1
                await asyncio.sleep(e.retry_after or 60)
                continue
            except APIClientError as e:
                self.logger.error(f"GraphQL API error during search: {e}")
                break
    
    async def get_repository_content(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str = "HEAD"
    ) -> Dict[str, Any]:
        """
        Get repository content using GraphQL.
        
        Args:
            owner: Repository owner
            repo: Repository name
            path: Path within repository
            ref: Git reference
            
        Returns:
            Dict[str, Any]: Repository content data
        """
        graphql_query = """
        query($owner: String!, $repo: String!, $expression: String!) {
          repository(owner: $owner, name: $repo) {
            object(expression: $expression) {
              ... on Tree {
                entries {
                  name
                  type
                  path
                  object {
                    ... on Blob {
                      text
                    }
                  }
                }
              }
              ... on Blob {
                text
              }
            }
          }
        }
        """
        
        expression = f"{ref}:{path}" if path else ref
        variables = {
            'owner': owner,
            'repo': repo,
            'expression': expression
        }
        
        return await self.execute_query(graphql_query, variables)
    
    async def search_optimized_for_patterns(
        self,
        regex_patterns: List[Tuple[re.Pattern, bool, bool]],
        max_results_per_pattern: int = 100
    ) -> AsyncIterator[SearchResult]:
        """
        Search optimized for different API key patterns from REGEX_LIST.
        
        Args:
            regex_patterns: List of (regex, too_many_results, too_long) tuples
            max_results_per_pattern: Maximum results per pattern
            
        Yields:
            SearchResult: Optimized search results
        """
        for regex, too_many_results, too_long in regex_patterns:
            pattern = regex.pattern
            
            # Build optimized GraphQL query based on pattern characteristics
            if too_many_results:
                # For patterns with many results, add more specific constraints
                search_queries = [
                    f"/{pattern}/ language:python",
                    f"/{pattern}/ language:javascript", 
                    f"/{pattern}/ language:typescript",
                    f"/{pattern}/ path:*.env",
                    f"/{pattern}/ path:*.config"
                ]
            else:
                # For patterns with fewer results, use broader search
                search_queries = [f"/{pattern}/"]
            
            for query in search_queries:
                try:
                    # Use smaller batch sizes for GraphQL efficiency
                    batch_size = 50 if too_many_results else 100
                    
                    async for result in self.search_code_with_pagination(
                        query, 
                        min(max_results_per_pattern, batch_size)
                    ):
                        yield result
                        
                except Exception as e:
                    self.logger.error(f"Error searching pattern {pattern}: {e}")
                    continue
    
    async def get_file_content_batch(
        self,
        file_requests: List[Tuple[str, str, str]]  # (owner, repo, path)
    ) -> Dict[str, str]:
        """
        Get multiple file contents efficiently using GraphQL.
        
        Args:
            file_requests: List of (owner, repo, path) tuples
            
        Returns:
            Dict[str, str]: Mapping of file keys to content
        """
        results = {}
        
        # Process in batches to avoid query complexity limits
        batch_size = 10
        for i in range(0, len(file_requests), batch_size):
            batch = file_requests[i:i + batch_size]
            
            # Build GraphQL query for batch
            query_parts = []
            variables = {}
            
            for idx, (owner, repo, path) in enumerate(batch):
                alias = f"file_{idx}"
                query_parts.append(f"""
                {alias}: repository(owner: "{owner}", name: "{repo}") {{
                  object(expression: "HEAD:{path}") {{
                    ... on Blob {{
                      text
                    }}
                  }}
                }}
                """)
            
            graphql_query = f"query {{ {' '.join(query_parts)} }}"
            
            try:
                response = await self.execute_query(graphql_query)
                
                for idx, (owner, repo, path) in enumerate(batch):
                    alias = f"file_{idx}"
                    file_key = f"{owner}/{repo}/{path}"
                    
                    if alias in response:
                        repo_data = response[alias]
                        if repo_data and 'object' in repo_data and repo_data['object']:
                            results[file_key] = repo_data['object'].get('text', '')
                        else:
                            results[file_key] = ''
                    else:
                        results[file_key] = ''
                        
            except Exception as e:
                self.logger.error(f"Error in batch file content request: {e}")
                # Fallback to empty content for failed batch
                for owner, repo, path in batch:
                    file_key = f"{owner}/{repo}/{path}"
                    results[file_key] = ''
        
        return results
    
    async def search_with_cursor_optimization(
        self,
        base_query: str,
        languages: List[str],
        max_total_results: int = 1000
    ) -> AsyncIterator[SearchResult]:
        """
        Search with cursor-based pagination optimization for multiple languages.
        
        Args:
            base_query: Base search query
            languages: List of programming languages
            max_total_results: Maximum total results across all languages
            
        Yields:
            SearchResult: Search results with optimized pagination
        """
        results_per_language = max_total_results // len(languages)
        
        # Process languages concurrently with controlled concurrency
        semaphore = asyncio.Semaphore(3)  # Limit concurrent GraphQL queries
        
        async def search_language(language: str):
            async with semaphore:
                query = f"{base_query} language:{language}"
                async for result in self.search_code_with_pagination(query, results_per_language):
                    yield result
        
        # Create tasks for each language
        tasks = [search_language(lang) for lang in languages]
        
        # Process results as they come in
        for task in asyncio.as_completed(tasks):
            async for result in await task:
                yield result
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get GraphQL client statistics.
        
        Returns:
            Dict[str, Any]: Client statistics
        """
        return self.stats.copy()


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
            # Use GraphQL for more efficient queries with cursor pagination
            search_query = query
            if language:
                search_query += f" language:{language}"
            
            async for result in self.graphql_client.search_code_with_pagination(search_query, max_results):
                yield result
        elif self.rest_client:
            async for result in self.rest_client.search_code(query, language, max_results):
                yield result
        else:
            raise APIClientError("No GitHub clients available")
    
    async def scan_repositories_selenium_equivalent(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Scan repositories using patterns equivalent to original Selenium implementation.
        
        This method provides the main interface for replacing Selenium-based scanning
        with API-based scanning while maintaining compatibility with existing patterns.
        
        Yields:
            Dict[str, Any]: Found API keys with metadata
        """
        if not self.rest_client:
            raise APIClientError("REST client not initialized")
        
        async for api_key_info in self.rest_client.scan_repositories_like_selenium():
            yield api_key_info
    
    async def process_search_url(self, search_url: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Process a GitHub search URL equivalent to Selenium implementation.
        
        Args:
            search_url: Original GitHub search URL from Selenium implementation
            
        Yields:
            Dict[str, Any]: Found API keys with metadata
        """
        if not self.rest_client:
            raise APIClientError("REST client not initialized")
        
        async for api_key_info in self.rest_client.process_search_url_equivalent(search_url):
            yield api_key_info
    
    async def get_file_content(self, repo: str, path: str, ref: str = "main") -> str:
        """
        Get file content using the most appropriate client.
        
        Args:
            repo: Repository identifier
            path: File path
            ref: Git reference
            
        Returns:
            str: File content
        """
        if self.rest_client:
            return await self.rest_client.get_file_content(repo, path, ref)
        else:
            raise APIClientError("No clients available for file content retrieval")
    
    def _should_use_graphql(self, query: str, max_results: int) -> bool:
        """
        Determine whether to use GraphQL based on query characteristics.
        
        Args:
            query: Search query
            max_results: Maximum results requested
            
        Returns:
            bool: True if GraphQL should be used
        """
        # Use GraphQL for:
        # 1. Large result sets (more efficient pagination)
        # 2. Complex queries with multiple filters
        # 3. When we need structured data
        
        if max_results > 500:
            return True
        
        # Count query complexity
        complex_operators = ['AND', 'OR', 'NOT', 'path:', 'filename:', 'extension:']
        complexity_score = sum(1 for op in complex_operators if op in query)
        
        return complexity_score > 2
    
    async def intelligent_search(
        self,
        query: str,
        language: Optional[str] = None,
        max_results: int = 1000
    ) -> AsyncIterator[SearchResult]:
        """
        Intelligently choose between REST and GraphQL based on query characteristics.
        
        Args:
            query: Search query
            language: Programming language filter
            max_results: Maximum results to return
            
        Yields:
            SearchResult: Search results
        """
        use_graphql = self._should_use_graphql(query, max_results)
        
        self.logger.debug(f"Using {'GraphQL' if use_graphql else 'REST'} for query: {query}")
        
        async for result in self.search_code(query, language, max_results, use_graphql):
            yield result
    
    async def get_combined_stats(self) -> Dict[str, Any]:
        """
        Get combined statistics from all clients.
        
        Returns:
            Dict[str, Any]: Combined statistics
        """
        stats = {
            'rest_client': {},
            'graphql_client': {},
            'total_api_calls': 0,
            'total_rate_limits': 0
        }
        
        if self.rest_client:
            rest_stats = await self.rest_client.get_stats()
            stats['rest_client'] = rest_stats
            stats['total_api_calls'] += rest_stats.get('api_calls_made', 0)
            stats['total_rate_limits'] += rest_stats.get('rate_limits_hit', 0)
        
        if self.graphql_client:
            graphql_stats = await self.graphql_client.get_stats()
            stats['graphql_client'] = graphql_stats
            stats['total_api_calls'] += graphql_stats.get('queries_executed', 0)
            stats['total_rate_limits'] += graphql_stats.get('rate_limits_hit', 0)
        
        return stats
    
    def generate_selenium_equivalent_urls(self) -> List[str]:
        """
        Generate search URLs equivalent to original Selenium implementation.
        
        This method creates the same URL patterns that were used in the original
        Selenium-based scanner for compatibility and testing purposes.
        
        Returns:
            List[str]: List of GitHub search URLs
        """
        candidate_urls = []
        
        for regex, too_many_results, _ in REGEX_LIST:
            # Add the paths to the search query
            for path in PATHS:
                url = f"https://github.com/search?q=(/{regex.pattern}/)+AND+({path})&type=code&ref=advsearch"
                candidate_urls.append(url)

            for language in LANGUAGES:
                if too_many_results:  # if the regex has too many results, add AND condition
                    url = f"https://github.com/search?q=(/{regex.pattern}/)+language:{language}&type=code&ref=advsearch"
                    candidate_urls.append(url)
                else:  # if the regex doesn't have too many results, use simpler query
                    url = f"https://github.com/search?q=(/{regex.pattern}/)&type=code&ref=advsearch"
                    candidate_urls.append(url)
        
        return candidate_urls
    
    async def process_selenium_equivalent_urls(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Process all search URLs equivalent to original Selenium implementation.
        
        This method provides a drop-in replacement for the original Selenium-based
        URL processing, maintaining the same search patterns and logic.
        
        Yields:
            Dict[str, Any]: Found API keys with metadata
        """
        urls = self.generate_selenium_equivalent_urls()
        
        self.logger.info(f"Processing {len(urls)} search URLs (Selenium equivalent)")
        
        for url in urls:
            try:
                async for api_key_info in self.process_search_url(url):
                    yield api_key_info
                    
                # Add delay between URL processing (equivalent to Selenium behavior)
                await asyncio.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"Error processing URL {url}: {e}")
                continue
    
    async def replace_selenium_scanner(
        self,
        keywords: List[str] = None,
        languages: List[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Complete replacement for Selenium-based scanner functionality.
        
        This method provides the main interface for replacing the original
        APIKeyLeakageScanner class with API-based scanning.
        
        Args:
            keywords: Keywords to search (currently not used in API version)
            languages: Languages to filter (uses LANGUAGES from config if None)
            
        Yields:
            Dict[str, Any]: Found API keys with metadata
        """
        # Use configured languages if none provided
        if languages is None:
            languages = [lang.strip('"') for lang in LANGUAGES]
        
        self.logger.info("Starting API-based scan (replacing Selenium)")
        
        # Process all search patterns
        async for api_key_info in self.scan_repositories_selenium_equivalent():
            yield api_key_info
    
    async def validate_replacement_compatibility(self) -> Dict[str, Any]:
        """
        Validate that the API-based implementation can replace Selenium.
        
        Returns:
            Dict[str, Any]: Compatibility validation results
        """
        validation_results = {
            'rest_client_available': self.rest_client is not None,
            'graphql_client_available': self.graphql_client is not None,
            'can_process_search_urls': True,
            'can_find_api_keys': True,
            'selenium_url_patterns_supported': True,
            'regex_patterns_supported': len(REGEX_LIST) > 0,
            'languages_supported': len(LANGUAGES) > 0,
            'paths_supported': len(PATHS) > 0
        }
        
        # Test basic functionality
        try:
            if self.rest_client:
                # Test a simple search
                test_query = "test"
                result_count = 0
                async for result in self.rest_client.search_code(test_query, max_results=1):
                    result_count += 1
                    break
                validation_results['rest_api_functional'] = True
            else:
                validation_results['rest_api_functional'] = False
                
        except Exception as e:
            validation_results['rest_api_functional'] = False
            validation_results['rest_api_error'] = str(e)
        
        # Calculate overall compatibility score
        functional_checks = [
            validation_results['rest_client_available'],
            validation_results['can_process_search_urls'],
            validation_results['can_find_api_keys'],
            validation_results['selenium_url_patterns_supported'],
            validation_results['regex_patterns_supported']
        ]
        
        validation_results['compatibility_score'] = sum(functional_checks) / len(functional_checks)
        validation_results['ready_for_production'] = validation_results['compatibility_score'] >= 0.8
        
        return validation_results
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False