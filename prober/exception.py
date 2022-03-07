"""Exceptions for the package."""


class ProberException(Exception):
    """General package exception"""


class ConfigSchemaError(ProberException):
    """Indicates that a read file does not match the prescribed schema."""


class ProbeException(ProberException):
    """General probe exception."""


class ProbeTimeout(ProbeException):
    """Indicates a probe timed out."""


class ICMPError(ProbeException):
    """Indicates an ICMP issue."""


class TCPError(ProbeException):
    """Indicates an ICMP issue."""


class ModemScrapeError(ProbeException):
    """Indicates something went wrong trying to scrape data from the modem info page."""


class NotAuthenticatedError(ModemScrapeError):
    """Indicates we're not authenticated to access some thing to do with a scrape."""
