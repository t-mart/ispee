"""Prometheus measuring functionality."""
from functools import partial
from typing import Callable

from prometheus_client import Counter, Histogram

from prober.console import CONSOLE
from prober.probe import icmp_ping_probe, tcp_syn_ack_probe

LABELS = ["destination", "type"]

PROBE_DURATION_SECONDS_HISTOGRAM = Histogram(  # type: ignore
    "probe_duration_seconds",
    "Histogram measuring speed with a TCP probe",
    LABELS,
)
PROBE_FAILURE_COUNTER = Counter(
    "probe_failure_total",
    "Counter for TCP probe failures (timeout, network error, etc)",
    LABELS,
)
PROBE_COUNTER = Counter(
    "probe_total",
    "Counter for TCP probe readings",
    LABELS,
)


def _record(
    *,
    measurement_fn: Callable[[], float],
    type_label: str,
    destination_label: str,
) -> None:
    """
    Generalized way of running one of the probes and recording it on a metric.
    """
    labels = {"type": type_label, "destination": destination_label}
    try:
        duration = measurement_fn()
        PROBE_DURATION_SECONDS_HISTOGRAM.labels(**labels).observe(  # type: ignore
            duration
        )
        CONSOLE.log(f"probe {labels}: {duration=}")
    except RuntimeError as run_err:
        PROBE_FAILURE_COUNTER.labels(**labels).inc()
        CONSOLE.log(f"probe {labels}: failure because {run_err}")

    PROBE_COUNTER.labels(**labels).inc()


def record_tcp_ping_probe(host: str, port: int) -> None:
    """
    Fire off a TCP probe against a host and set the prometheus metrics accordingly.
    """
    _record(
        measurement_fn=partial(tcp_syn_ack_probe, host=host, dest_port=port),
        type_label="tcp-ping",
        destination_label=f"{host}:{port}",
    )


def record_icmp_ping_probe(host: str) -> None:
    """
    Fire off an ICMP probe against a host and set the prometheus metrics accordingly.
    """
    _record(
        measurement_fn=partial(
            icmp_ping_probe,
            host=host,
            check_identifier=False,  # strangely, numerous hosts fail these checks
            check_sequence_number=False,  # probably bad ICMP implementation?
        ),
        type_label="icmp-ping",
        destination_label=f"{host}",
    )
