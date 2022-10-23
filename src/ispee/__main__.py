"""Main module of the checker."""
from pathlib import Path

import click
from anyio import create_task_group, run
from prometheus_client import start_http_server

from ispee.config import get_config
from ispee.console import CONSOLE
from ispee.jobs import IPJob, MetricJob, PingJob, S33ScrapeJob

DEFAULT_HTTP_SERVER_PORT = 8000
DEFAULT_CONFIG_PATH = Path("/etc/ispee/config.yml")


async def start_jobs(jobs: list[MetricJob]) -> None:
    async with create_task_group() as task_group:
        for job in jobs:
            task_group.start_soon(job.run)


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
    start_http_server(port)
    CONSOLE.log(f"Prometheus metrics exposed on HTTP server with port {port}.")

    config = get_config(config_path=config_path)

    jobs: list[MetricJob] = []

    for ping_config in config.pings:
        for type_ in ping_config.types:
            if type_ == "icmp":
                jobs.append(
                    PingJob.build_icmp_ping_job(
                        host=ping_config.host, name=ping_config.name
                    )
                )
            elif type_ == "dns-udp":
                jobs.append(
                    PingJob.build_dns_ping_job(
                        host=ping_config.host, name=ping_config.name, dns_type="udp"
                    )
                )
            elif type_ == "dns-tcp":
                jobs.append(
                    PingJob.build_dns_ping_job(
                        host=ping_config.host, name=ping_config.name, dns_type="tcp"
                    )
                )

    if config.arris_s33_modem_config:
        arris_s33_modem_config = config.arris_s33_modem_config
        host = arris_s33_modem_config.host
        password = arris_s33_modem_config.password
        jobs.append(S33ScrapeJob.build(host=host, password=password))

    if config.ip:
        jobs.append(IPJob.build())

    run(start_jobs, jobs)


if __name__ == "__main__":
    main.main()
