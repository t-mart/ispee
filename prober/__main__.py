"""Main module of the checker."""
import click
from prometheus_client import start_http_server

from pathlib import Path
from prober.config import read_metric_jobs
from prober.console import CONSOLE
import trio

DEFAULT_HTTP_SERVER_PORT = 8000
DEFAULT_CONFIG_PATH = Path("/etc/prober/config.yml")


async def start_jobs(config_path: Path) -> None:
    async with trio.open_nursery() as nursery:
        for metric_job in read_metric_jobs(config_path):
            nursery.start_soon(metric_job.async_measure)


@click.command()
@click.option(
    "-p",
    "--port",
    default=DEFAULT_HTTP_SERVER_PORT,
    show_default=True,
    help="Run the prometheus HTTP server on this port",
)
@click.option(
    "--config-path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Load configuration from this path",
)
def main(port: int, config_path: Path) -> None:
    """
    Expose an HTTP server on port 8000 that publishes probe metrics in Prometheus
    format.
    """
    start_http_server(port)  # type: ignore
    CONSOLE.log(f"Prometheus metrics exposed on HTTP server with port {port}.")

    trio.run(start_jobs, config_path)


if __name__ == "__main__":
    main.main()
