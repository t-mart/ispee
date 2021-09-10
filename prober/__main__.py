"""Main module of the checker."""
import threading
import time

import click
from prometheus_client import start_http_server

from prober.console import CONSOLE
from prober.config import get_config_probe_record_fns

HTTP_SERVER_PORT = 8000
DELAY_INTERVAL_SECONDS = 15


@click.command()
def main() -> None:
    """
    Expose an HTTP server on port 8000 that publishes connectivity metrics in Prometheus
    format.
    """
    probe_record_fns = list(get_config_probe_record_fns())
    CONSOLE.log(f"Found {len(probe_record_fns)} in config file.")

    start_http_server(HTTP_SERVER_PORT)
    CONSOLE.log(
        f"Prometheus metrics exposed on HTTP server with port {HTTP_SERVER_PORT}."
    )

    CONSOLE.log(f"Starting record loop on {DELAY_INTERVAL_SECONDS} second interval.")
    while True:
        for fn in probe_record_fns:
            thread = threading.Thread(
                target=fn,
                daemon=True,
            )
            thread.start()
        time.sleep(DELAY_INTERVAL_SECONDS)


if __name__ == "__main__":
    main.main()
