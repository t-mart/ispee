"""Prometheus measuring functionality."""
from __future__ import annotations

from functools import partial
from typing import Callable, ClassVar
from abc import abstractmethod, ABC
from trio_util import periodic

from attrs import define, frozen
from prometheus_client import Counter, Gauge, Histogram

from prober.console import CONSOLE
from prober.exception import ProbeException
from prober.probe import icmp_ping_probe, tcp_syn_ack_probe
from prober.s33 import S33Scraper
import trio

@frozen(kw_only=True)
class MetricJob(ABC):
    """Static type checking protocol for metric jobs"""

    description: str
    frequency_seconds: float

    async def async_measure(self) -> None:
        CONSOLE.log(f"Starting {self} job on a {self.frequency_seconds} frequency")
        async for _ in periodic(self.frequency_seconds):
            await trio.to_thread.run_sync(self.measure)

    @abstractmethod
    def measure(self) -> None:
        """Take a measurement and record it to a prometheus metric."""
        ...


PROBE_LABELS = ["destination", "type"]

PROBE_DURATION_SECONDS_HISTOGRAM = Histogram(  # type: ignore
    "probe_duration_seconds",
    "Histogram measuring speed with a TCP probe",
    PROBE_LABELS,
)
PROBE_FAILURE_COUNTER = Counter(
    "probe_failure_total",
    "Counter for TCP probe failures (timeout, network error, etc)",
    PROBE_LABELS,
)
PROBE_COUNTER = Counter(
    "probe_total",
    "Counter for TCP probe readings",
    PROBE_LABELS,
)


@define
class ProbeMetricJob(MetricJob):
    """Represents a job that can record some probe metric."""

    description: str
    _probe_fn: Callable[[], float]
    _labels: dict[str, str]

    FREQUENCY_SECONDS: ClassVar[float] = 15

    @classmethod
    def build_tcp_ping(cls, host: str, port: int, name: str) -> MetricJob:
        """Create a TCP ping metric job."""
        probe_fn = partial(tcp_syn_ack_probe, host=host, dest_port=port)
        labels = {"type": "tcp-ping", "destination": f"{host}:{port}-{name}"}

        # unfortunately, there's a coupling between the input arguments of this function
        # and the expected labels of the prom gauges/counters we will update. so, we do
        # this assertion to make one's not been updated without updating the other
        assert set(labels) == set(
            PROBE_LABELS
        ), "TCP ping probe job configured with wrong labels, report bug"

        return cls(
            description=f"probe tcp {host=} {port=}",
            probe_fn=probe_fn,
            labels=labels,
            frequency_seconds=cls.FREQUENCY_SECONDS,
        )

    @classmethod
    def build_icmp_ping(cls, host: str, name: str) -> MetricJob:
        """Create a ICMP ping metric job."""
        probe_fn = partial(icmp_ping_probe, host=host)
        labels = {"type": "icmp-ping", "destination": f"{host}-{name}"}

        # ditto as above in tcp_ping_probe_job
        assert set(labels) == set(
            PROBE_LABELS
        ), "ICMP ping probe job configured with wrong labels, report bug"

        return cls(
            description=f"probe icmp {host=}",
            probe_fn=probe_fn,
            labels=labels,
            frequency_seconds=cls.FREQUENCY_SECONDS,
        )

    def measure(self) -> None:
        """
        Run the probe and record the result (with labels). If it's successful, the time
        it took is added to the PROBE_DURATION_SECONDS_HISTOGRAM. Otherwise, the
        PROBE_FAILURE_COUNTER is incremented. And no matter what, PROBE_COUNTER is
        incremented.
        """
        # pylint: disable=protected-access
        try:
            duration = self._probe_fn()
            PROBE_DURATION_SECONDS_HISTOGRAM.labels(  # type: ignore
                **self._labels
            ).observe(duration)
            CONSOLE.log(
                f"{PROBE_DURATION_SECONDS_HISTOGRAM._name}{self._labels}: {duration=}"
            )
        except ProbeException as probe_exc:
            PROBE_FAILURE_COUNTER.labels(**self._labels).inc()
            CONSOLE.log(
                f"{PROBE_FAILURE_COUNTER._name}{self._labels}: incremented because "
                f"{probe_exc}"
            )

        PROBE_COUNTER.labels(**self._labels).inc()
        CONSOLE.log(f"{PROBE_COUNTER._name}{self._labels}: incremented")


CHANNEL_LABELS = ["frequency_megahertz", "host"]

CHANNEL_POWER_GAUGE = Gauge(  # type: ignore
    "power_dbmv",
    "Power in decibels per millivolt",
    CHANNEL_LABELS,
)
CHANNEL_SNR_GAUGE = Gauge(  # type: ignore
    "snr_db",
    "Signal to noise ratio in decibels",
    CHANNEL_LABELS,
)
# this is such a tragedy: the next corrected/uncorrectables metrics are really counters
# that mostly go up, but sometimes reset to 0 after reboot (or overflow?). but, the
# interface for Counter objects only let you increment, not set (as on Gauge objects).
# But, we really need set because we're just scraping a modem info page that only
# reports total counts at the current moment.
#
# ideally, we'd instrument the modem to expose prometheus metrics so it could increment
# a counter properly, but we don't have access to that code (nor would we want to even
# if we did... it's probably low level C firmware, etc.)
#
# so instead, we just treat these counts as gauges. yikes. however, i think under the
# hood, Counter and Gauge metrics are represented the same..., it's just the
# instrumentation API imposes this fuckery. so, in grafana, you can still call
# "increase()" on guages as long as you know its really a counter.
CHANNEL_CORRECTED_GAUGE = Gauge(  # type: ignore
    "corrected_codewords_total",
    "Number of corrected codewords",
    CHANNEL_LABELS,
)
CHANNEL_UNCORRECTABLE_GAUGE = Gauge(  # type: ignore
    "uncorrectable_codewords_total",
    "Number of corrected codewords",
    CHANNEL_LABELS,
)


@define
class ArrisS33ModemMetricJob(MetricJob):
    """Represents a job that can record some probe metric."""

    description: str
    _scraper: S33Scraper

    FREQUENCY_SECONDS: ClassVar[float] = 15

    @classmethod
    def build(cls, host: str, password: str) -> MetricJob:
        """Create a modem metric job."""
        return cls(
            description=f"modem_info {host=}",
            scraper=S33Scraper(host=host, password=password),
            frequency_seconds=cls.FREQUENCY_SECONDS,
        )

    def measure(self) -> None:
        """
        Get the channel info and record it. Updates will be made to CHANNEL_POWER_GAUGE,
        CHANNEL_SNR_GAUGE, CHANNEL_CORRECTED_GAUGE, and CHANNEL_UNCORRECTABLE_GAUGE.
        """
        # pylint: disable=protected-access
        downstream_channels, _ = self._scraper.get_channel_info()
        for chan in downstream_channels:
            labels = {
                "host": self._scraper.host,
                # the labels are too hard to read in Hz, so convert to MHz
                "frequency_megahertz": str(chan.frequency_hz // 10**6),
            }

            CHANNEL_POWER_GAUGE.labels(**labels).set(chan.power_dbmv)  # type: ignore
            CONSOLE.log(
                f"{CHANNEL_SNR_GAUGE._name}{labels} " f"power_dbmv={chan.power_dbmv}"
            )

            CHANNEL_SNR_GAUGE.labels(**labels).set(chan.snr_db)  # type: ignore
            CONSOLE.log(f"{CHANNEL_SNR_GAUGE._name}{labels} " f"snr_db={chan.snr_db}")

            CHANNEL_CORRECTED_GAUGE.labels(**labels).set(  # type: ignore
                chan.corrected_codewords_total
            )
            CONSOLE.log(
                f"{CHANNEL_CORRECTED_GAUGE._name}{labels} "
                f"corrected_codewords_total={chan.corrected_codewords_total}"
            )

            CHANNEL_UNCORRECTABLE_GAUGE.labels(**labels).set(  # type: ignore
                chan.uncorrectable_codewords_total
            )
            CONSOLE.log(
                f"{CHANNEL_UNCORRECTABLE_GAUGE._name}{labels} "
                f"uncorrectable_codewords_total={chan.uncorrectable_codewords_total}"
            )
