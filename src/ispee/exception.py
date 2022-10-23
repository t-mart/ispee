"""Exceptions for the package."""


class ISPeeError(Exception):
    """General package exception"""


class ConfigSchemaError(ISPeeError):
    """Indicates that a read file does not match the prescribed schema."""


class PingError(ISPeeError):
    """General ping errors"""


class TimeoutError(PingError):
    """Indicates a probe timed out."""


class ModemScrapeError(ISPeeError):
    """Indicates something went wrong trying to scrape data from the modem info page."""
