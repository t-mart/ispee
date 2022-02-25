"""Main module of the checker."""
import threading
import time

import click
from prometheus_client import start_http_server

from prober.config import read_metric_jobs
from prober.console import CONSOLE
from prober.prometheus import MetricJob

HTTP_SERVER_PORT = 8000
DELAY_INTERVAL_SECONDS = 15


@click.command()
@click.option(
    "--use-threads/--no-use-threads",
    default=True,
    show_default=True,
    help=(
        "Use threading (recommended) or not. If not, probes run sequentially, which "
        "will make the probe interval inconsistent."
    ),
)
def main(use_threads: bool) -> None:
    """
    Expose an HTTP server on port 8000 that publishes probe metrics in Prometheus
    format.
    """
    metric_jobs: list[MetricJob] = []
    for metric_job in read_metric_jobs():
        metric_jobs.append(metric_job)
        CONSOLE.log(f"Read job {metric_job} from config file.")

    start_http_server(HTTP_SERVER_PORT)  # type: ignore
    CONSOLE.log(
        f"Prometheus metrics exposed on HTTP server with port {HTTP_SERVER_PORT}."
    )

    CONSOLE.log(f"Starting record loop on {DELAY_INTERVAL_SECONDS} second interval.")
    while True:
        for metric_job in metric_jobs:
            if use_threads:
                thread = threading.Thread(
                    target=metric_job.record,
                    daemon=True,
                )
                thread.start()
            else:
                metric_job.record()
        time.sleep(DELAY_INTERVAL_SECONDS)


if __name__ == "__main__":
    main.main(auto_envvar_prefix="PROBER")
