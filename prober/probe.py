"""
Probe functionality.
"""

# TODO: check checksums? with scapy?
# TODO: remove tcp syn-ack check because any response indicates it's ok
# TODO: try again with scapy send and recv?

import random
import socket
import struct
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from scapy.layers.inet import ICMP, IP, TCP

from prober.exception import ICMPError, ProbeTimeout, TCPError

# from scapy.layers.inet import UDP


DEFAULT_TIMEOUT_SECONDS = 5.0


def _randint_bits(n_bits: int) -> int:
    """Return a number from 0 to 2^n_bits -1 inclusive."""
    return random.randint(0, (2**n_bits) - 1)


class SocketTimeoutPool:
    """
    Limits cumulative socket operations to an initial amount/pool of timeout time for
    socket operations performed inside limit() contexts. It is imperative that the
    context is only used for a single socket.send*/socket.recv* call for the best
    precision -- no other code should be inside the context.

    For example, for an initial pool of 5 seconds:

        sock_time = SocketTimeoutPool(initial_pool_seconds=5)
        with sock_time.limit(sock):
            # limit() function has set timeout to 5 seconds (sock.settimeout(5))
            sock.send(b"hi")

        # ^ let's say that took 1.5 seconds to complete ^

        # then later...
        with sock_time.limit(sock):
            # sock now has timeout of 3.5 seconds (5 - 1.5 = 3.5)
            sock.recv(1024)

        # and so on...

    Otherwise, you're having to both 1) call socket.settimeout() and 2) measure how much
    time was actually used and decrease that from the next socket.settimeout() call.

    While this time tracking is more convenient, do note that SocketTimeoutPool
    conflates time-in-context with time-waiting-for-socket. But they are not the same
    thing. For example, the bit of time Python spends entering and exiting the context
    will decrease from the timeout pool. In other words, the time tracking will not be
    precise, but should be close enough.

    The rationale for class is abstraction. At a high level, you can promise your caller
    that "this function will take at most n seconds", more or less, even though the
    underlying socket calls will have different timeouts set.
    """

    def __init__(self, initial_pool_seconds: float) -> None:
        self.seconds_left = initial_pool_seconds

    @contextmanager
    def limit(self, sock: socket.socket) -> Iterator[None]:
        """
        Provides a context that a few things:
        - Before entering the context, the socket's timeout to the remaining time left.
          If there is no time left, a ProbeTimeout exception is raised.
        - Importantly, any TimeoutErrors (from the stdlib) that bubble from the context
          are transformed to ProbeTimeout exceptions.
        - After exiting the context, deducts the amount of time spent inside the context
          from the remaining time left.

        Only one blocking socket operation must be attempted inside the context (or else
        the timeout durations will not be correctly set.)
        """
        if self.seconds_left <= 0:
            raise ProbeTimeout("Probe operation timed out")

        sock.settimeout(self.seconds_left)

        start = time.perf_counter()

        try:
            yield
        except TimeoutError as timeout_error:
            raise ProbeTimeout("Probe operation timed out") from timeout_error

        self.seconds_left -= time.perf_counter() - start


def icmp_ping_probe(
    host: str,
    identifier: Optional[int] = None,
    sequence_number: Optional[int] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    """
    Return the time it takes to make a ICMP ping with a given sequence_number and
    identifier.

    In the reply, the sequence_number and identifier are expected to match those from
    the response. This function will continue to wait for such a response until the
    timeout has expired, at which a ProbeTimeout exception will be raised. If the
    sequence_number and identifier do match a reply but the type and code are non-zero,
    an ICMPError will be raised (this indicates problems were encountered talking to the
    host).

    Finally, there are probably additional failure cases that I'm not considering, so
    this behavior should not be considered authoritative.

    Requires Linux and root.

    References:
    - http://www.networksorcery.com/enp/protocol/icmp.htm
    - http://www.networksorcery.com/enp/protocol/ip.htm
    - https://www.binarytides.com/python-syn-flood-program-raw-sockets-linux/
    - https://scapy.readthedocs.io/en/latest/usage.html#tcp-ping
    - https://docs.microsoft.com/en-us/windows/win32/winsock/tcp-ip-raw-sockets-2
    """
    if identifier is None:
        identifier = _randint_bits(16)
    if sequence_number is None:
        sequence_number = _randint_bits(16)

    with socket.socket(
        family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_ICMP
    ) as sock:

        timeout_pool = SocketTimeoutPool(timeout_seconds)

        # type 8, code 0 means icmp echo request
        # for later matching to the right reply, set a custom id and sequence number
        tx_dgram_header = ICMP(type=8, code=0, id=identifier, seq=sequence_number)
        # set payload to our timer, host will respond with it
        tx_dgram = tx_dgram_header / struct.pack("!d", time.perf_counter())

        with timeout_pool.limit(sock):
            # dummy port 0 bc AF_INET requirement of (addr, port) format. icmp is
            # port-less
            sock.sendto(bytes(tx_dgram), (host, 0))

        # enter loop where we check packets. I didn't know this, but it's necessary to
        # loop because it's very possible to receive data destined for other readers. I
        # suppose this is consequence of raw sockets?
        while True:
            # i'm not really sure what recv returns... can we guarantee it's a complete
            # packet? testing indicates as much. also, must the buffer size be a certain
            # size? 2048 should more than enough for our ICMP, so crossing fingers
            with timeout_pool.limit(sock):
                rx_packet_bytes = sock.recv(2048)

            # record time now, do processing later
            dgram_recv_time = time.perf_counter()

            rx_packet = IP(rx_packet_bytes)

            # ensure we're not receiving some other protocol, else the decoding below
            # will fail. (note: is this even possible?)
            if rx_packet.proto != socket.IPPROTO_ICMP:
                continue

            # one obvious omission is the check of the IP packet source. But, we don't
            # want to do that for ICMP because hops along the way may be responsible for
            # the reply (for example, if the host is unreachable)

            rx_dgram: ICMP = rx_packet.payload

            if rx_dgram.id != identifier or rx_dgram.seq != sequence_number:
                # we very possibly may be getting someone else's ping reply
                continue

            if rx_dgram.type == 0 and rx_dgram.code == 0:
                # success case
                dgram_send_time: float = struct.unpack("!d", bytes(rx_dgram.payload))[0]
                return dgram_recv_time - dgram_send_time

            # otherwise, probably something like destination unreachable or ttl exceed
            raise ICMPError(
                f"In ICMP reply, got type={rx_dgram.type} and code={rx_dgram.code}"
            )


def tcp_syn_ack_probe(
    host: str,
    dest_port: int,
    sequence_number: Optional[int] = None,
    acknowledgment_number: Optional[int] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> float:
    """
    Return the time it takes to make a "TCP SYN" ping. This sends a TCP SYN segment to a
    host on a destination port and awaits either a SYN-ACK response with the properly
    updated sequence and acknowledgement numbers or the expiration of the timeout.

    In the response, if the flags are not equal to SYN-ACK, a TCPError is raised.

    An initial total of timeout_seconds are shared among all socket operations. If the
    timeout is depleted while performing a socket operation, a ProbeTimeout exception is
    raised.

    Finally, there are probably additional failure cases that I'm not considering.

    Requires Linux and root.

    References:
    - http://www.networksorcery.com/enp/protocol/tcp.htm
    - http://www.networksorcery.com/enp/protocol/ip.htm
    - https://www.binarytides.com/python-syn-flood-program-raw-sockets-linux/
    - https://scapy.readthedocs.io/en/latest/usage.html#tcp-ping
    - https://docs.microsoft.com/en-us/windows/win32/winsock/tcp-ip-raw-sockets-2
    """
    if sequence_number is None:
        sequence_number = _randint_bits(32)
    if acknowledgment_number is None:
        acknowledgment_number = _randint_bits(32)

    with socket.socket(
        family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_TCP
    ) as sock:

        # provide IP packet too. see IP_HDRINCL note below for reasoning
        tx_packet = IP(dst=host) / TCP(
            dport=dest_port,
            flags="S",
            seq=sequence_number,
            ack=acknowledgment_number,
        )

        timeout_pool = SocketTimeoutPool(timeout_seconds)

        # tell the kernel that we will provide the network-level (IP protocol) header.
        # this might not be needed (ICMP doesn't need it for some reason), but more
        # because I can't figure out how to get it work without it: unless this is set,
        # we don't seem to get any data back in our recv() calls.
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

        tx_time = time.perf_counter()

        with timeout_pool.limit(sock):
            sock.sendto(bytes(tx_packet), (host, dest_port))

        while True:

            with timeout_pool.limit(sock):
                rx_packet_bytes = sock.recv(2048)

            # record time now, do processing later
            rx_time = time.perf_counter()

            rx_packet = IP(_pkt=rx_packet_bytes)

            # ensure we're not receiving some other protocol, else the decoding below
            # will fail. (note: is this even possible?)
            if rx_packet.proto != socket.IPPROTO_TCP:
                continue

            # ensure source is correct
            if rx_packet.src != host:
                continue

            rx_dgram: TCP = rx_packet.payload

            # server swaps seq and ack with ack and seq+1
            exp_seq = acknowledgment_number
            exp_ack = (sequence_number + 1) % (2**32)
            if rx_dgram.seq != exp_seq and rx_dgram.ack != exp_ack:
                continue

            # server should be SYN-ACKing back
            if rx_dgram.flags == "SA":
                return rx_time - tx_time

            # prolly an issue if server isn't SYN-ACKing
            raise TCPError(
                f"host did not respond with correct flags "
                f"(expected: SYN-ACK, actual: {rx_dgram.flags})"
            )


# NOTE: THIS CODE DOES NOT WORK. I see the response ICMP datagram in wireshark,
# but can't access it in code for some reason. I am keeping it in source code for
# posterity.
# def udp_probe(
#     host: str,
#     dest_port: int,
#     src_port: Optional[int] = None,
#     timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
# ) -> float:
#     """
#     Return the time it takes to make a "UDP" ping. By sending a UDP datagram to a host
#     on port 0, you can illicit an ICMP port unreachable reply (code=3, type=3).

#     NOTE: Many hosts will not respond to this type of ping.
#     """
#     if src_port is None:
#         src_port = _randint_bits(16)

#     with socket.socket(
#         family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_UDP
#     ) as sock:

#         tx_packet = IP(dst=host) / UDP(
#             sport=src_port,
#             dport=dest_port,
#         )

#         cumul_socket_timeout = CumulativeSocketTimeout(sock, timeout_seconds)

#         # tell the kernel that we will provide the network-level (IP protocol) header.
#         # this might not be needed (ICMP doesn't need it for some reason), but more
#         # because I can't figure out how to get it work without it: unless this is
#         #set, we don't seem to get any data back in our recv() calls.
#         sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

#         tx_time = time.perf_counter()

#         with cumul_socket_timeout.settimeout():
#             sock.sendto(bytes(tx_packet), (host, dest_port))

#         while True:

#             with cumul_socket_timeout.settimeout():
#                 rx_packet_bytes = sock.recv(2048)

#             # record time now, do processing later
#             rx_time = time.perf_counter()

#             rx_packet = IP(_pkt=rx_packet_bytes)

#             # ensure we're not receiving some other protocol, else the decoding below
#             # will fail. (note: is this even possible?)
#             if rx_packet.proto != socket.IPPROTO_ICMP:
#                 continue

#             # ensure source is correct
#             if rx_packet.src != host:
#                 continue

#             rx_dgram: ICMP = rx_packet.payload

#             if rx_dgram.type == 3 and rx_dgram.code == 3:
#                 return rx_time - tx_time
#             else:
#                 continue
