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
