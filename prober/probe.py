"""
Probe functionality.
"""
import random
import socket
import time
from typing import Optional

from scapy.layers.inet import ICMP, IP, TCP

DEFAULT_TIMEOUT_SECONDS = 5


def tcp_syn_ack_probe(
    host: str,
    dest_port: int,
    src_port: Optional[int] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    check_flags: bool = True,
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
        sock.sendto(bytes(tx_packet), ("8.8.8.8", dest_port))
        try:
            # ask for enough bytes to get the IP and TCP headers (I think), and as
            # suggested by the python docs, should be a power of two.
            # note: it's possible we still get fewer bytes than we need. not gonna think
            # about that right now.
            rx_packet_bytes = sock.recv(64)
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
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    check_type: bool = True,
    check_code: bool = True,
    check_identifier: bool = True,
    check_sequence_number: bool = True,
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

    # type 8, code 0 is the standard for icmp echo requests
    # and, for matching to the right reply, you can set a custom id and sequence number
    tx_msg = ICMP(type=8, code=0, id=identifier, seq=sequence_number)

    with socket.socket(
        family=socket.AF_INET, type=socket.SOCK_RAW, proto=socket.IPPROTO_ICMP
    ) as sock:
        sock.settimeout(timeout_seconds)
        start = time.perf_counter()
        sock.sendto(bytes(tx_msg), (host, 0))  # dummy port
        try:
            rx_msg_bytes = sock.recv(64)
        except TimeoutError as timeout_err:
            raise RuntimeError(f"host timed out: {timeout_err}") from timeout_err

        duration = time.perf_counter() - start

    rx_packet = IP(rx_msg_bytes)
    rx_msg = rx_packet.payload

    if rx_msg.type != 0 and check_type:
        raise RuntimeError(
            "host did not respond with correct ICMP type "
            f"(expected: 0, actual: {rx_msg.type}"
        )
    if rx_msg.code != 0 and check_code:
        raise RuntimeError(
            "host did not respond with correct ICMP code "
            f"(expected: 0, actual: {rx_msg.code}"
        )

    if rx_msg.id != identifier and check_identifier:
        raise RuntimeError(
            "host did not respond with correct ICMP identifier "
            f"(expected={identifier}, actual={rx_msg.id})"
        )

    if rx_msg.seq != sequence_number and check_sequence_number:
        raise RuntimeError(
            "host did not respond with correct ICMP sequence number "
            f"(expected={sequence_number}, actual={rx_msg.seq})"
        )

    return duration
