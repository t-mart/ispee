"""
IP getter
"""

import dns.asyncquery
import dns.asyncresolver
import dns.exception
import dns.message
from dns.resolver import LifetimeTimeout

DEFAULT_TIMEOUT_SECONDS = 5.0


async def get_self_ip(
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    # this is a special lookup, which returns your own IP
    host = "ns1.google.com"
    name = "o-o.myaddr.l.google.com"
    record_type = "TXT"

    # first, resolve host
    try:
        answers = await dns.asyncresolver.resolve(
            host, "A", lifetime=DEFAULT_TIMEOUT_SECONDS
        )
    except LifetimeTimeout as lifetime_timeout:
        raise TimeoutError("timed out brah") from lifetime_timeout
    host_ip = next(iter(answers)).address  # get first record's address

    query = dns.message.make_query(name, record_type)
    try:
        response = await dns.asyncquery.tcp(query, host_ip, timeout=timeout_seconds)
    except OSError as os_error:
        raise TimeoutError(str(os_error)) from os_error
    my_ip = (
        [record for rrset in response.answer for record in rrset][0]
        .strings[0]
        .decode("utf-8")
    )
    return my_ip  # type: ignore
