"""
Probe functionality.
"""
import random
import socket
import time
from typing import Optional
from collections.abc import Iterable
from contextlib import contextmanager
import struct

from scapy.layers.inet import ICMP, IP, TCP

DEFAULT_TIMEOUT_SECONDS = 5.0


class CumulativeSocketTimeout:
    """
    Facilitates cumulative socket operations against an initial amount of timeout time.
    For example, if you want a sequence of send()s and recv()s to complete in 5 seconds,
    you'd use the context manager provided by the settimeout() method and this object
    will call settimeout on the socket appropriately for each subsequent socket
    operation.

    Otherwise, you're having to both 1) call socket.settimeout() and 2) measure how much
    time was actually used and decrease that from the next socket.settimeout() call.
    """

    def __init__(self, sock: socket.socket, initial_timeout_seconds: float) -> None:
        self.sock = sock
        self.timeout_seconds_left = initial_timeout_seconds

    @contextmanager
    def settimeout(self) -> Iterable[None]:
        """
        Provides a context that does two things:
        - before entering the context, the socket's timeout to the remaining time left,
        - on context manager close, deducts the amount of time spent inside the context
        from the remaining time left.

        Only one blocking socket operation must be attempted inside the context (or else
        each operation will have an equal amount of time.)
        """
        if self.expired:
            raise TimeoutError("No time left")

        self.sock.settimeout(self.timeout_seconds_left)

        start = time.perf_counter()

        yield

        self.timeout_seconds_left -= time.perf_counter() - start

    @property
    def expired(self) -> bool:
        """Returns False if there's no time left."""
        return self.timeout_seconds_left <= 0


def tcp_syn_ack_probe(
    host: str,
    dest_port: int,
    src_port: Optional[int] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    # check_flags: bool = True,
) -> float:
    """
    Return the time it takes to make a "TCP SYN" ping.

    This sends a TCP SYN segment to a host with a source and destination port and awaits
    a SYN-ACK response. If the src_port is None, one is chosen at random.

    In the response, if the flags are not equal to SYN-ACk, a RuntimeError is raised.
    However, this check may be controlled with the check_flags parameter.

    Additionally, if the timeout is exceeded while waiting for data, a RuntimeError is
    raised.

    Finally, there are probably additional failure cases that I'm not considering.

    References:
    - http://www.networksorcery.com/enp/protocol/tcp.htm
    - http://www.networksorcery.com/enp/protocol/ip.htm
    - https://www.binarytides.com/python-syn-flood-program-raw-sockets-linux/

    Requires Linux and root.
    """
    if src_port is None:
        src_port = random.randint(0, 2**16 - 1)

    # Scapy is just used for datagram encoding and decoding, not sending or receiving.
    # We'll create the socket ourselves so we don't need to do any pcap stuff that scapy
    # uses.
    tx_packet = IP(dst=host) / TCP(sport=src_port, dport=dest_port, flags="S")

    with socket.socket(
        family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_TCP
    ) as sock:
        sock.settimeout(timeout_seconds)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

        start = time.perf_counter()
        # wierd that we must set host and port here too when our datagram already
        # defines it.
        sock.sendto(bytes(tx_packet), (host, dest_port))
        try:
            # ask for enough bytes to get the IP and TCP headers (I think), and as
            # suggested by the python docs, should be a power of two.
            # note: it's possible we still get fewer bytes than we need. not gonna think
            # about that right now.
            rx_packet_bytes = sock.recv(2048)
        except TimeoutError as timeout_err:
            raise RuntimeError(f"host timed out: {timeout_err}") from timeout_err

        # stop timing asap, do post processing later
        duration = time.perf_counter() - start

    rx_packet = IP(_pkt=rx_packet_bytes)
    if rx_packet.payload.flags != "SA" and check_flags:
        raise RuntimeError(
            f"host did not respond with correct flags "
            f"(expected: SYN-ACK, actual: {rx_packet.payload.flags})"
        )

    return duration


# this isn't quite working for some reason
# there's is idea of a UDP ping where you send a UDP datagran to a closed remote port,
# and instead of receiving some kind of UDP response, you get a ICMP type 3 (destination
# unreachable), code 3 (port unreachable error). I guess I'm not sure how to open a
# socket with both socket.IPPROTO_UDP to send and socket.IPPROTO_ICMP to receive? shrug
# def udp_probe(
#     host: str,
#     dest_port: int,
#     src_port: Optional[int] = None,
#     timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
# ) -> float:
#     """
#     Return the time it takes to make a "UDP" ping.
#     """
#     HOST = "192.168.1.151"
#
#     tx_datagram = IP(dst=HOST)/UDP(dport=0, sport=1234)
#     with socket.socket(
#         family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_UDP
#     ) as sock:
#         sock.settimeout(5)
#         sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
#         print(f"sending {bytes(tx_datagram)}")
#         sock.sendto(bytes(tx_datagram), (HOST, 0))

#         recv = sock.recv(128)
#         print(recv)
#         rx_datagram = IP(_pkt=recv)
#         rx_datagram.show()


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
    the response and the type and code must be zero. If not, a RuntimeError is raised.
    However, these checks may be controlled with the check_* parameters.

    Additionally, if the timeout is exceeded while waiting for data, a RuntimeError is
    raised.

    Finally, there are probably additional failure cases that I'm not considering.

    Requires Linux and root.
    """
    if identifier is None:
        identifier = random.randint(0, 2**16 - 1)
    if sequence_number is None:
        sequence_number = random.randint(0, 2**16 - 1)

    with socket.socket(
        family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_ICMP
    ) as sock:

        cumul_socket_timeout = CumulativeSocketTimeout(sock, timeout_seconds)

        tx_dgram_payload = struct.pack("!d", time.perf_counter())
        # type 8, code 0 means icmp echo request
        # for later matching to the right reply, set a custom id and sequence number
        tx_dgram_header = ICMP(type=8, code=0, id=identifier, seq=sequence_number)
        # set payload to our timer
        tx_dgram = tx_dgram_header / tx_dgram_payload

        with cumul_socket_timeout.settimeout():
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
            with cumul_socket_timeout.settimeout():
                rx_packet_bytes = sock.recv(2048)

            rx_packet = IP(rx_packet_bytes)

            # ensure we're not receiving some other protocol, else the decoding below
            # will fail. (note: is this even possible?)
            if rx_packet.proto != socket.IPPROTO_ICMP:
                continue

            rx_dgram: ICMP = rx_packet.payload

            if rx_dgram.id != identifier or rx_dgram.seq != sequence_number:
                # we very possible may be getting someone else's ping reply
                continue

            if rx_dgram.type == 0 and rx_dgram.code == 0:
                # success case
                now = time.perf_counter()
                before: float = struct.unpack("!d", bytes(rx_dgram.payload))[0]
                return now - before

            # otherwise, probably something like destination unreachable or ttl exceed
            raise RuntimeError(
                f"In ICMP reply, got type={rx_dgram.type} and code={rx_dgram.code}"
            )
