"""
Ping functionality.
"""

from typing import Literal, TypeAlias

import dns.asyncquery
import dns.exception
import dns.message
from icmplib import async_ping

from ispee.exception import PingError, TimeoutError

DEFAULT_TIMEOUT_SECONDS = 5.0

DNS_PING_TYPES: TypeAlias = Literal["tcp", "udp"]


async def icmp_ping(
    host: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    """
    Return the time it takes to make a ICMP ping.
    """
    response = await async_ping(host, count=1, timeout=timeout_seconds)

    if response.packet_loss > 0:
        raise TimeoutError(f"icmp ping to {host} timed out (>{timeout_seconds}s)")

    return response.avg_rtt / 1000  # type: ignore


async def dns_ping(
    host: str,
    dns_type: DNS_PING_TYPES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    """
    Return the time it takes to make a DNS query to host of its own IP. (silly,
    but its quick)
    """
    query = dns.message.make_query(host, "A")

    if dns_type == "udp":
        coro = dns.asyncquery.udp(query, host, timeout=timeout_seconds)
    elif dns_type == "tcp":
        coro = dns.asyncquery.tcp(query, host, timeout=timeout_seconds)
    else:
        raise ValueError("invalid dns_type")

    try:
        response = await coro
    except dns.exception.Timeout:
        raise TimeoutError(
            f"dns {dns_type} ping to {host} timed out (>{timeout_seconds}s)"
        )
    except ConnectionRefusedError as conn_ref:
        raise PingError(f"connection refused: {conn_ref}")
    return response.time  # type: ignore
