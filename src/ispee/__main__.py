"""Main module of the checker."""
from collections.abc import Iterable, Sequence
from pathlib import Path

import click
import prometheus_client
import uvicorn
from anyio import create_task_group, run
from anyio.abc import CancelScope

from ispee.async_util import CancellableTask
from ispee.config import Config, get_config
from ispee.console import CONSOLE
from ispee.jobs import IPJob, MetricJob, PingJob, S33ScrapeJob

DEFAULT_HTTP_SERVER_PORT = 8000
DEFAULT_CONFIG_PATH = Path("/etc/ispee/config.yml")


async def start_tasks(tasks: Iterable[CancellableTask]) -> None:
    async with create_task_group() as task_group:
        for task in tasks:
            task_group.start_soon(task, task_group.cancel_scope)


def get_config_jobs(config: Config) -> Iterable[MetricJob]:
    for ping_config in config.pings:
        for type_ in ping_config.types:
            if type_ == "icmp":
                yield PingJob.build_icmp_ping_job(
                    host=ping_config.host, name=ping_config.name
                )
            elif type_ == "dns-udp":
                yield PingJob.build_dns_ping_job(
                    host=ping_config.host, name=ping_config.name, dns_type="udp"
                )
            elif type_ == "dns-tcp":
                yield PingJob.build_dns_ping_job(
                    host=ping_config.host, name=ping_config.name, dns_type="tcp"
                )

    if config.arris_s33_modem_config:
        arris_s33_modem_config = config.arris_s33_modem_config
        host = arris_s33_modem_config.host
        password = arris_s33_modem_config.password
        yield S33ScrapeJob.build(host=host, password=password)

    if config.ip:
        yield IPJob.build()


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

    async def start_prometheus_server(cancel_scope: CancelScope) -> None:
        config = uvicorn.Config(
            prometheus_client.make_asgi_app,
            port=port,
            log_level="info",
            factory=True,
            host="0.0.0.0",
        )
        server = uvicorn.Server(config)
        CONSOLE.log(f"Prometheus metrics exposed on HTTP server with port {port}.")
        await server.serve()

        # this is a little hack: uvicorn greedily handles Ctrl-C and doesn't propogate
        # the signal/KeyboardInterrupt up. For event loops, where other forever-tasks
        # are running, this means the application is not "shutdownable".
        #
        # To workaround that, if we're at this point here, the server has shutdown and
        # the task is about done. Before that, we cancel all other tasks. Then, Python
        # can naturally exit.
        await cancel_scope.cancel()

    config = get_config(config_path=config_path)

    tasks: Sequence[CancellableTask] = [start_prometheus_server] + [
        job.loop for job in get_config_jobs(config)
    ]

    run(start_tasks, tasks)


if __name__ == "__main__":
    main.main()
