"""Custom exceptions for the Homevolt library."""


class HomevoltException(Exception):
    """Base exception for all Homevolt errors."""

    pass


class HomevoltConnectionError(HomevoltException):
    """Raised when there's a connection or network error."""

    pass


class HomevoltAuthenticationError(HomevoltException):
    """Raised when authentication fails."""

    pass


class HomevoltDataError(HomevoltException):
    """Raised when there's an error parsing or processing data."""

    pass

