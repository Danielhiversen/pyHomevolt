"""Custom exceptions for the Homevolt library."""


class HomevoltError(Exception):
    """Base exception for all Homevolt errors."""

    pass


class HomevoltConnectionError(HomevoltError):
    """Raised when there's a connection or network error."""

    pass


class HomevoltAuthenticationError(HomevoltError):
    """Raised when authentication fails."""

    pass


class HomevoltDataError(HomevoltError):
    """Raised when there's an error parsing or processing data."""

    pass

