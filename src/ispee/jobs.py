"""Prometheus measuring functionality."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import partial
from typing import ClassVar

import anyio
from attrs import frozen
from prometheus_client import Counter, Gauge, Histogram, Info

from ispee.console import CONSOLE
from ispee.exception import PingError
from ispee.ip import get_self_ip
from ispee.ping import DNS_PING_TYPES, dns_ping, icmp_ping
from ispee.s33 import S33Scraper


async def periodic(period: float) -> AsyncIterator[None]:
    """
    Yields once every `period` seconds, taking account the time spent in the loop.

    If the loop takes >= `period` seconds, run the next iteration immediately.
    """
    now = await anyio.current_time()
    while True:
        yield
        await anyio.sleep_until(now + period)
        now = await anyio.current_time()


@frozen(kw_only=True)
class MetricJob(ABC):
    """Static type checking protocol for metric jobs"""

    frequency_seconds: float

    async def loop(self, cancel_scope: anyio.CancelScope) -> None:
        """Call measure() every frequency_seconds in a loop."""
        CONSOLE.log(f"Starting {self} job on a {self.frequency_seconds} frequency")
        async for _ in periodic(self.frequency_seconds):
            # if we haven't coded specifically for this case, log it and try again?
            try:
                await self.measure()
            except Exception as exc:
                CONSOLE.log(f"{self} measure() failed because unhandled {exc}")
                continue

    @abstractmethod
    async def measure(self) -> None:
        """Take a measurement and record it to a prometheus metric."""
        ...


@frozen(kw_only=True)
class PingJob(MetricJob):
    LABELS: ClassVar[list[str]] = ["destination", "type"]
    PING_DURATION_SECONDS_HISTOGRAM: ClassVar[Histogram] = Histogram(
        "ping_duration_seconds",
        "Histogram measuring latency with a ping",
        LABELS,
    )
    PING_FAILURE_COUNTER: ClassVar[Counter] = Counter(
        "ping_failure_total",
        "Counter for ping failures (timeout, network error, etc)",
        LABELS,
    )
    PING_COUNTER: ClassVar[Counter] = Counter(
        "ping_total",
        "Counter for total pings",
        LABELS,
    )

    FREQUENCY_SECONDS: ClassVar[float] = 15

    probe_fn: Callable[[], Awaitable[float]]
    labels: dict[str, str]

    @classmethod
    def build_icmp_ping_job(cls, host: str, name: str) -> PingJob:
        probe_fn = partial(icmp_ping, host=host)
        labels = {"type": "icmp-ping", "destination": f"{host}-{name}"}

        return cls(
            probe_fn=probe_fn,
            labels=labels,
            frequency_seconds=cls.FREQUENCY_SECONDS,
        )

    @classmethod
    def build_dns_ping_job(
        cls, host: str, dns_type: DNS_PING_TYPES, name: str
    ) -> PingJob:
        probe_fn = partial(dns_ping, host=host, dns_type=dns_type)
        labels = {"type": f"{dns_type}-dns-ping", "destination": f"{host}-{name}"}

        return cls(
            probe_fn=probe_fn,
            labels=labels,
            frequency_seconds=cls.FREQUENCY_SECONDS,
        )

    async def measure(self) -> None:
        try:
            duration = await self.probe_fn()
        except PingError as ping_error:
            self.PING_FAILURE_COUNTER.labels(**self.labels).inc()
            CONSOLE.log(
                f"{self.PING_FAILURE_COUNTER}{self.labels}: incremented because "
                f"{ping_error}"
            )
        else:
            self.PING_DURATION_SECONDS_HISTOGRAM.labels(**self.labels).observe(duration)
            CONSOLE.log(
                f"{self.PING_DURATION_SECONDS_HISTOGRAM._name}{self.labels}: "
                f"{duration=}"
            )

        self.PING_COUNTER.labels(**self.labels).inc()
        CONSOLE.log(f"{self.PING_COUNTER._name}{self.labels}: incremented")


@frozen(kw_only=True)
class S33ScrapeJob(MetricJob):

    LABELS: ClassVar[list[str]] = ["frequency_megahertz", "host"]

    CHANNEL_POWER_GAUGE: ClassVar[Gauge] = Gauge(
        "power_dbmv",
        "Power in decibels per millivolt",
        LABELS,
    )
    CHANNEL_SNR_GAUGE: ClassVar[Gauge] = Gauge(
        "snr_db",
        "Signal to noise ratio in decibels",
        LABELS,
    )
    # this is such a tragedy: the next corrected/uncorrectables metrics are really
    # counters that mostly go up, but sometimes reset to 0 after reboot (or overflow?).
    # but, the interface for Counter objects only let you increment, not set (as on
    # Gauge objects). But, we really need set because we're just scraping a modem info
    # page that only reports total counts at the current moment
    #
    # the problem is we can't "instrument" the modem: we're just a 3rd party scraper
    #
    # so instead, we just treat these counts as gauges. yikes. however, i think under
    # the hood, Counter and Gauge metrics are represented the same..., it's just the
    # instrumentation API imposes this fuckery. so, in grafana, you can still call
    # "increase()" on guages as long as you know its really a counter.
    CHANNEL_CORRECTED_GAUGE: ClassVar[Gauge] = Gauge(
        "corrected_codewords_total",
        "Number of corrected codewords",
        LABELS,
    )
    CHANNEL_UNCORRECTABLE_GAUGE: ClassVar[Gauge] = Gauge(
        "uncorrectable_codewords_total",
        "Number of corrected codewords",
        LABELS,
    )

    FREQUENCY_SECONDS: ClassVar[float] = 15

    scraper: S33Scraper

    @classmethod
    def build(cls, host: str, password: str) -> S33ScrapeJob:
        """Create a modem metric job."""
        return cls(
            scraper=S33Scraper(host=host, password=password),
            frequency_seconds=cls.FREQUENCY_SECONDS,
        )

    async def measure(self) -> None:
        """
        Get the channel info and record it. Updates will be made to CHANNEL_POWER_GAUGE,
        CHANNEL_SNR_GAUGE, CHANNEL_CORRECTED_GAUGE, and CHANNEL_UNCORRECTABLE_GAUGE.
        """
        # pylint: disable=protected-access
        downstream_channels, _ = await self.scraper.get_channel_info()
        for chan in downstream_channels:
            labels = {
                "host": self.scraper.host,
                # the labels are too hard to read in Hz, so convert to MHz
                "frequency_megahertz": str(chan.frequency_hz // 10**6),
            }

            self.CHANNEL_POWER_GAUGE.labels(**labels).set(chan.power_dbmv)
            CONSOLE.log(
                f"{self.CHANNEL_SNR_GAUGE._name}{labels} "
                f"power_dbmv={chan.power_dbmv}"
            )

            self.CHANNEL_SNR_GAUGE.labels(**labels).set(chan.snr_db)
            CONSOLE.log(
                f"{self.CHANNEL_SNR_GAUGE._name}{labels} " f"snr_db={chan.snr_db}"
            )

            self.CHANNEL_CORRECTED_GAUGE.labels(**labels).set(
                chan.corrected_codewords_total
            )
            CONSOLE.log(
                f"{self.CHANNEL_CORRECTED_GAUGE._name}{labels} "
                f"corrected_codewords_total={chan.corrected_codewords_total}"
            )

            self.CHANNEL_UNCORRECTABLE_GAUGE.labels(**labels).set(
                chan.uncorrectable_codewords_total
            )
            CONSOLE.log(
                f"{self.CHANNEL_UNCORRECTABLE_GAUGE._name}{labels} "
                f"uncorrectable_codewords_total={chan.uncorrectable_codewords_total}"
            )


@frozen(kw_only=True)
class IPJob(MetricJob):
    INFO: ClassVar[Info] = Info(
        name="ip", documentation="Records current own IP address"
    )

    FREQUENCY_SECONDS: ClassVar[float] = 60

    @classmethod
    def build(cls) -> IPJob:
        return cls(frequency_seconds=cls.FREQUENCY_SECONDS)

    async def measure(self) -> None:
        labels = {"ip": await get_self_ip()}
        self.INFO.info(labels)
        CONSOLE.log(f"ip{labels}: incremented ")
