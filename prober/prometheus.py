"""Prometheus measuring functionality."""
from __future__ import annotations

from functools import partial
from typing import Callable

from attrs import define
from prometheus_client import Counter, Histogram

from prober.console import CONSOLE
from prober.probe import icmp_ping_probe, tcp_syn_ack_probe
from prober.exception import ProbeException

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


@define
class MetricJob:
    """Represents a job that can record how a probe performed."""

    measure_fn: Callable[[], float]
    type_label: str
    destination_label: str

    @classmethod
    def tcp_ping_job(cls, host: str, port: int) -> MetricJob:
        """Create a TCP ping metric job."""
        return cls(
            measure_fn=partial(tcp_syn_ack_probe, host=host, dest_port=port),
            type_label="tcp-ping",
            destination_label=f"{host}:{port}",
        )

    @classmethod
    def icmp_ping_job(cls, host: str) -> MetricJob:
        """Create a ICMP ping metric job."""
        return cls(
            measure_fn=partial(icmp_ping_probe, host=host),
            type_label="icmp-ping",
            destination_label=f"{host}",
        )

    @property
    def label_dict(self) -> dict[str, str]:
        """Return a dict of the labels that will be attached to data from this job."""
        return {"type": self.type_label, "destination": self.destination_label}

    def record(self) -> None:
        """
        Run the probe and record the result (with labels). If it's successful, the time
        it took is added to the PROBE_DURATION_SECONDS_HISTOGRAM. Otherwise, the
        PROBE_FAILURE_COUNTER is incremented. And no matter what, PROBE_COUNTER is
        incremented.
        """
        try:
            duration = self.measure_fn()
            PROBE_DURATION_SECONDS_HISTOGRAM.labels(  # type: ignore
                **self.label_dict
            ).observe(duration)
            CONSOLE.log(f"probe {self}: {duration=}")
        except ProbeException as probe_exc:
            PROBE_FAILURE_COUNTER.labels(**self.label_dict).inc()
            CONSOLE.log(f"probe {self}: failure because {probe_exc}")

        PROBE_COUNTER.labels(**self.label_dict).inc()

    def __str__(self) -> str:
        return str(self.label_dict)

    def __repr__(self) -> str:
        return str(self)
