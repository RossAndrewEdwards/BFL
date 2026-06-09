class ValidationError(ValueError):
    """Base exception for all domain and user input validation errors."""
    pass


class QuotaExceededError(ValidationError):
    """Exception raised when a league capacity or slot quota is exceeded."""
    pass
