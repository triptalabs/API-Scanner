"""
Custom exceptions for async components.

This module defines specific exceptions used throughout the async scanner
components to provide clear error handling and debugging information.
"""


class AsyncScannerError(Exception):
    """Base exception for async scanner components."""
    
    def __init__(self, message: str, details: dict = None) -> None:
        """
        Initialize async scanner error.
        
        Args:
            message: Error message
            details: Optional additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self) -> str:
        """String representation of the error."""
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class RateLimitError(AsyncScannerError):
    """Exception raised when rate limits are exceeded."""
    
    def __init__(
        self, 
        message: str = "Rate limit exceeded", 
        retry_after: int = None,
        service: str = None
    ) -> None:
        """
        Initialize rate limit error.
        
        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
            service: Service that imposed the rate limit
        """
        details = {}
        if retry_after is not None:
            details['retry_after'] = retry_after
        if service is not None:
            details['service'] = service
        
        super().__init__(message, details)
        self.retry_after = retry_after
        self.service = service


class ValidationError(AsyncScannerError):
    """Exception raised during API key validation."""
    
    def __init__(
        self, 
        message: str, 
        key_hash: str = None,
        validation_type: str = None
    ) -> None:
        """
        Initialize validation error.
        
        Args:
            message: Error message
            key_hash: Hash of the API key that failed validation
            validation_type: Type of validation that failed
        """
        details = {}
        if key_hash is not None:
            details['key_hash'] = key_hash
        if validation_type is not None:
            details['validation_type'] = validation_type
        
        super().__init__(message, details)
        self.key_hash = key_hash
        self.validation_type = validation_type


class CacheError(AsyncScannerError):
    """Exception raised during cache operations."""
    
    def __init__(
        self, 
        message: str, 
        operation: str = None,
        cache_key: str = None
    ) -> None:
        """
        Initialize cache error.
        
        Args:
            message: Error message
            operation: Cache operation that failed
            cache_key: Cache key involved in the operation
        """
        details = {}
        if operation is not None:
            details['operation'] = operation
        if cache_key is not None:
            details['cache_key'] = cache_key
        
        super().__init__(message, details)
        self.operation = operation
        self.cache_key = cache_key


class APIClientError(AsyncScannerError):
    """Exception raised by API clients."""
    
    def __init__(
        self, 
        message: str, 
        status_code: int = None,
        response_body: str = None,
        endpoint: str = None
    ) -> None:
        """
        Initialize API client error.
        
        Args:
            message: Error message
            status_code: HTTP status code
            response_body: Response body from the API
            endpoint: API endpoint that failed
        """
        details = {}
        if status_code is not None:
            details['status_code'] = status_code
        if response_body is not None:
            details['response_body'] = response_body
        if endpoint is not None:
            details['endpoint'] = endpoint
        
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body
        self.endpoint = endpoint


class ConfigurationError(AsyncScannerError):
    """Exception raised for configuration-related errors."""
    
    def __init__(
        self, 
        message: str, 
        config_key: str = None,
        config_value: str = None
    ) -> None:
        """
        Initialize configuration error.
        
        Args:
            message: Error message
            config_key: Configuration key that caused the error
            config_value: Configuration value that caused the error
        """
        details = {}
        if config_key is not None:
            details['config_key'] = config_key
        if config_value is not None:
            details['config_value'] = config_value
        
        super().__init__(message, details)
        self.config_key = config_key
        self.config_value = config_value