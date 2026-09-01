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


class HomevoltCommandRejectedError(HomevoltDataError):
    """Raised when the device console rejects a command."""

    pass


class HomevoltCommandVerificationError(HomevoltDataError):
    """Raised when device state does not match an accepted command."""

    pass


class HomevoltCommandOutcomeUnknownError(HomevoltConnectionError):
    """Raised when a mutation may have succeeded but cannot be verified."""

    pass
