"""Custom exceptions for CUPT."""


class CuptError(Exception):
    """Base exception for all CUPT errors."""


class APIError(CuptError):
    """Raised when the ClickUp API returns an error or the request fails."""


class AuthError(CuptError):
    """Raised when authentication is missing or invalid."""


class ConfigError(CuptError):
    """Raised when configuration is missing or malformed."""
